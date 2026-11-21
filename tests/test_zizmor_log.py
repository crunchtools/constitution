"""The zizmor job log in scripts/zizmor_log.py, read back from SARIF."""

import json

import zizmor_log as Z


def finding(rule: str, uri: str, line: int, level: str = "error") -> dict:
    return {
        "ruleId": rule,
        "level": level,
        "message": {"text": f"{rule} here"},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": line}}}
        ],
    }


def test_each_finding_is_one_line_then_the_count():
    report = {
        "runs": [
            {
                "results": [
                    finding("zizmor/unpinned-uses", ".github/workflows/ci.yml", 8),
                    finding("zizmor/artipacked", ".github/workflows/ci.yml", 8, "note"),
                ]
            }
        ]
    }
    assert Z.lines(report) == [
        "error[zizmor/unpinned-uses] .github/workflows/ci.yml:8: zizmor/unpinned-uses here",
        "note[zizmor/artipacked] .github/workflows/ci.yml:8: zizmor/artipacked here",
        "zizmor: 2 finding(s)",
    ]


def test_a_clean_report_says_so():
    assert Z.lines({"runs": [{"results": []}]}) == ["zizmor: 0 finding(s)"]


def test_a_finding_without_a_region_still_prints():
    bare = {"ruleId": "zizmor/x", "message": {"text": "m"}, "locations": [{}]}
    assert Z.lines({"runs": [{"results": [bare]}]}) == [
        "warning[zizmor/x] ?:?: m",
        "zizmor: 1 finding(s)",
    ]


def test_main_reads_the_file(tmp_path, capsys):
    sarif = tmp_path / "zizmor.sarif"
    sarif.write_text(json.dumps({"runs": [{"results": [finding("zizmor/r", "a.yml", 3)]}]}))
    assert Z.main(["zizmor_log.py", str(sarif)]) == 0
    assert (
        capsys.readouterr().out == "error[zizmor/r] a.yml:3: zizmor/r here\nzizmor: 1 finding(s)\n"
    )
