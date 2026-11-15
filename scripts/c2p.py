#!/usr/bin/env python3
"""c2p.py COMPONENT_DEFINITION REPORTS DRY_RUN OUT_DIR - both engines, one assessment results.

Runs in C2P's own environment (.cache/c2p, scripts/install-tools.sh), not
in the one requirements.lock describes: C2P 1.0.0 needs compliance-trestle
3.x (docs/decisions/0005). scripts/evidence.py starts it with that
environment's Python.

Reads:
  COMPONENT_DEFINITION  oscal/component-definition.json: the rules, and the
                        checks each engine declares for them
  REPORTS               a directory holding Kyverno's PolicyReports and
                        ClusterPolicyReports as `kubectl get -o json` returned
                        them, unchanged (policyreports.json,
                        clusterpolicyreports.json)
  DRY_RUN               what the API server answered when each running pod
                        was sent again as a server-side dry run
                        (scripts/dryrun.py), one outcome per check and pod

Writes, as C2P writes them:
  OUT_DIR/assessment-results.json  one OSCAL assessment results for both
                                   engines: C2P's kyverno-cel plugin on the
                                   reports, its vap plugin on the dry run,
                                   aggregated by C2P (C2P.add_pvp_result);
                                   every observation names its rule and the
                                   check, so the engine behind it
  OUT_DIR/posture.json             C2P's control-level posture over those
                                   results (c2p-posture/v1): each control's
                                   state and how many of its expected
                                   checks reported

Nothing here judges a control; scripts/evidence.py does, and reads both.
Exits 2 when C2P fails or any input cannot be read.
"""
import json
import os
import pathlib
import sys

C2P_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "c2p", "src")
sys.path.insert(0, C2P_SRC)

from c2p.framework.c2p import C2P  # noqa: E402
from c2p.framework.models import RawResult  # noqa: E402
from c2p.framework.models.c2p_config import C2PConfig, ComplianceOscal  # noqa: E402
from c2p.tools.posture import posture, render  # noqa: E402
from c2p.tools.posture.model import Source  # noqa: E402
from plugins_public.plugins.kyverno_cel import PluginKyvernoCel  # noqa: E402
from plugins_public.plugins.vap import PluginVap  # noqa: E402
from trestle.oscal.component import ComponentDefinition  # noqa: E402


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__.split("\n")[0])
    cd, reports, dry_run, out = sys.argv[1:]
    try:
        items = []
        for name in ("policyreports.json", "clusterpolicyreports.json"):
            items += json.load(open(os.path.join(reports, name))).get("items") or []
        outcomes = json.load(open(dry_run))
        config = C2PConfig()
        config.compliance = ComplianceOscal(component_definition=cd)
        config.result_title = "Kyverno's PolicyReports and the API server's dry run, through C2P"
        config.result_description = ("C2P 1.0.0: its kyverno-cel plugin on Kyverno's PolicyReports, its vap "
                                     "plugin on the API server's answers to a server-side dry run of each "
                                     "running pod, aggregated into one assessment results.")
        c2p = C2P(config)
        kyverno = PluginKyvernoCel().generate_pvp_result(RawResult(data=items))
        api_server = PluginVap().generate_pvp_result(RawResult(data=outcomes))
        c2p.add_pvp_result(kyverno)
        c2p.add_pvp_result(api_server)
        ar = c2p.result_to_oscal()
    except Exception as e:  # C2P that cannot produce its results is no evidence
        print(f"C2P failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
    os.makedirs(out, exist_ok=True)
    ar_path = os.path.join(out, "assessment-results.json")
    with open(ar_path, "w") as f:
        f.write(ar.oscal_serialize_json(pretty=True))
        f.write("\n")
    try:
        doc = posture.generate([ar], ComponentDefinition.oscal_read(pathlib.Path(cd)),
                               source=Source(assessment_results="assessment-results.json",
                                             component_definition=os.path.basename(cd)))
    except Exception as e:
        print(f"C2P's posture failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
    with open(os.path.join(out, "posture.json"), "w") as f:
        f.write(render.render_json(doc))
        f.write("\n")
    observations = ar.results[0].observations or []
    print(f"== C2P: one assessment results, {len(observations)} observations with "
          f"{sum(len(o.subjects or []) for o in observations)} subjects: "
          f"{len(kyverno.observations_by_check or [])} from Kyverno's reports, "
          f"{len(api_server.observations_by_check or [])} from the API server's dry run")


if __name__ == "__main__":
    main()
