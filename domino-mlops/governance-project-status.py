#!/usr/bin/env python3
"""Report whether a Domino governance bundle is fully complete.

A bundle is complete when all of the following hold:
  - every approval is Approved or ConditionallyApproved
  - every required, visible evidence artifact (other than guidance text) has
    a latest result
  - no finding is still open (anything other than Done or WontDo)

Prints JSON. Exit code: 0 all bundles complete, 1 something incomplete,
2 error (bad arguments, bundle not found, API failure).
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

PASSED_APPROVALS = {"Approved", "ConditionallyApproved"}
CLOSED_FINDINGS = {"Done", "WontDo"}
PAGE_SIZE = 100


def load_auth():
    spec = importlib.util.spec_from_file_location(
        "domino_auth", Path(__file__).with_name("domino-auth.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load_auth()


def list_bundles(session, base_url, project_name):
    """All active bundles whose projectName matches exactly (no name filter in the API)."""
    bundles, offset = [], 0
    while True:
        resp = auth.api_request(
            session,
            "GET",
            f"{base_url}/api/governance/v1/bundles",
            params={"state": "Active", "search": project_name, "limit": PAGE_SIZE, "offset": offset},
        ).json()
        data = resp.get("data") or []
        bundles += [b for b in data if b.get("projectName") == project_name]
        offset += PAGE_SIZE
        if offset >= resp.get("meta", {}).get("pagination", {}).get("totalCount", 0) or not data:
            return bundles


def required_artifacts(policy):
    """Yield (evidence_id, artifact_id, stage_name, evidence_name) for required evidence needing a result."""
    for stage in policy.get("stages") or []:
        evidence_items = list(stage.get("evidenceSet") or [])
        evidence_items += [a["evidence"] for a in stage.get("approvals") or [] if a.get("evidence")]
        for evidence in evidence_items:
            if evidence.get("visible") is False:
                continue
            for artifact in evidence.get("artifacts") or []:
                if (
                    artifact.get("required")
                    and artifact.get("visible", True)
                    and artifact.get("artifactType") != "guidance"
                ):
                    yield evidence.get("id"), artifact.get("id"), stage.get("name"), evidence.get("name")


def check_bundle(session, base_url, bundle):
    approvals = auth.api_request(
        session, "GET", f"{base_url}/api/governance/v1/bundles/{bundle['id']}/approvals"
    ).json()
    approval_report = [{"name": a.get("name"), "status": a.get("status")} for a in approvals]

    missing_evidence, open_findings = [], []
    policies = [p for p in bundle.get("policies") or [] if not p.get("deactivatedAt")]
    if not policies and bundle.get("policyId"):
        policies = [{"policyId": bundle["policyId"], "policyVersionId": bundle.get("policyVersionId")}]
    for bp in policies:
        body = {"bundleId": bundle["id"], "policyId": bp["policyId"]}
        if bp.get("policyVersionId"):
            body["policyVersionId"] = bp["policyVersionId"]
        computed = auth.api_request(
            session, "POST", f"{base_url}/api/governance/v1/rpc/compute-policy", json=body
        ).json()

        latest = {
            (r.get("evidenceId"), r.get("artifactId"))
            for r in computed.get("results") or []
            if r.get("isLatest")
        }
        for evidence_id, artifact_id, stage, evidence_name in required_artifacts(computed.get("policy") or {}):
            if (evidence_id, artifact_id) not in latest:
                missing_evidence.append(
                    {"policy": bp.get("policyName"), "stage": stage, "evidence": evidence_name, "artifactId": artifact_id}
                )

        findings = (computed.get("findingsInfo") or {}).get("approvalFindingsMap") or {}
        for approval_id, items in findings.items():
            for f in items or []:
                if f.get("status") not in CLOSED_FINDINGS:
                    open_findings.append({"approvalId": approval_id, "findingId": f.get("id"), "status": f.get("status")})

    complete = (
        bool(approvals)
        and all(a["status"] in PASSED_APPROVALS for a in approval_report)
        and not missing_evidence
        and not open_findings
    )
    return {
        "bundleName": bundle.get("name"),
        "bundleId": bundle["id"],
        "complete": complete,
        "approvals": approval_report,
        "missingEvidence": missing_evidence,
        "openFindings": open_findings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-name", required=True, help="Domino project name")
    parser.add_argument(
        "--bundle-name", required=True, help="governance bundle name; comma-separate to check several"
    )
    auth.add_auth_args(parser)
    args = parser.parse_args()

    wanted = [n.strip() for n in args.bundle_name.split(",") if n.strip()]
    if not wanted:
        auth.fail("--bundle-name must contain at least one name")

    session, base_url = auth.get_session(args.url, args.token)
    bundles = list_bundles(session, base_url, args.project_name)
    by_name = {b.get("name"): b for b in bundles}
    missing = [n for n in wanted if n not in by_name]
    if missing:
        auth.fail(
            f"bundle(s) not found in project '{args.project_name}': {', '.join(missing)}. "
            f"Active bundles there: {', '.join(sorted(n for n in by_name if n)) or '(none)'}"
        )

    results = [check_bundle(session, base_url, by_name[n]) for n in wanted]
    overall = all(r["complete"] for r in results)
    print(json.dumps({"project": args.project_name, "complete": overall, "bundles": results}, indent=2))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
