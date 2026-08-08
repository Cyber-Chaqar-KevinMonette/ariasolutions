"""
qa/runner.py — Run the test suite and capture a structured report.

We use pytest's --junit-xml output as the bridge: pytest stays pytest,
we read the XML, and the consumer gets a typed report. This avoids
re-implementing test discovery, fixture management, parametrization,
and parallelism that pytest already does correctly.

The runner is sync and returns a TestReport. The caller decides whether
to render it, JSON-serialise it, or pipe it into score_test_report() for
a 0-100 quality number.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TestFailure:
    """One failed (or errored) test case from the run."""
    name: str
    classname: str
    duration_s: float
    message: str           # short failure message
    detail: str            # full traceback / error text


@dataclass
class TestReport:
    """Structured result of one test run."""
    started_at: str
    finished_at: str
    duration_s: float
    target: str                                       # path passed to pytest
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    raw_xml_path: str | None = None
    pytest_exit_code: int | None = None

    @property
    def pass_rate(self) -> float:
        """Fraction in [0,1]. 1.0 == perfect run."""
        denom = self.total - self.skipped
        if denom <= 0:
            return 0.0
        return self.passed / denom

    def render(self) -> str:
        status = "✓" if self.failed == 0 and self.errored == 0 else "✗"
        lines = [
            f"{status} test run · {self.target} · {self.duration_s:.2f}s",
            f"  total: {self.total}  passed: {self.passed}  "
            f"failed: {self.failed}  errored: {self.errored}  skipped: {self.skipped}",
            f"  pass rate: {self.pass_rate * 100:.1f}%",
        ]
        if self.failures:
            lines.append("")
            lines.append(f"  failures ({len(self.failures)}):")
            for f in self.failures[:20]:
                lines.append(f"    ✗ {f.classname}::{f.name}")
                if f.message:
                    msg = f.message.strip().splitlines()[0][:120]
                    lines.append(f"        {msg}")
            if len(self.failures) > 20:
                lines.append(f"    ... and {len(self.failures) - 20} more")
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def run_tests(
    target: str | Path = "tests/",
    *,
    keyword: str | None = None,
    timeout_s: float = 600.0,
    extra_args: list[str] | None = None,
) -> TestReport:
    """Run pytest against ``target`` and return a structured TestReport.

    ``target`` may be a directory, single test file, or a pytest nodeid
    like ``tests/test_people.py::TestUpsert``.

    ``keyword`` is forwarded to pytest's -k. Combine with ``target`` to
    narrow.

    The XML output file is kept on disk so the caller can keep / archive it.
    """
    started = _utc_now()
    started_t = datetime.now(timezone.utc)

    xml_fd, xml_path = tempfile.mkstemp(prefix="qa-junit-", suffix=".xml")
    Path(xml_path)  # ensure path object usable
    # Close the OS fd; pytest writes the file itself
    import os
    os.close(xml_fd)

    cmd = [
        sys.executable, "-m", "pytest",
        str(target),
        "-q", "--tb=short",
        f"--junit-xml={xml_path}",
    ]
    if keyword:
        cmd.extend(["-k", keyword])
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout_s,
            check=False,
        )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        return TestReport(
            started_at=started,
            finished_at=_utc_now(),
            duration_s=timeout_s,
            target=str(target),
            errored=1,
            failures=[TestFailure(
                name="<timeout>", classname="qa.runner",
                duration_s=timeout_s,
                message=f"pytest timeout after {timeout_s}s",
                detail="",
            )],
            pytest_exit_code=-1,
            raw_xml_path=xml_path,
        )

    finished = _utc_now()
    duration = (datetime.now(timezone.utc) - started_t).total_seconds()

    report = TestReport(
        started_at=started,
        finished_at=finished,
        duration_s=duration,
        target=str(target),
        raw_xml_path=xml_path,
        pytest_exit_code=exit_code,
    )

    if not Path(xml_path).exists() or Path(xml_path).stat().st_size == 0:
        # pytest crashed before writing XML — capture stderr as a single error
        report.errored = 1
        report.total = 1
        report.failures.append(TestFailure(
            name="<pytest-startup>", classname="qa.runner",
            duration_s=duration,
            message="pytest produced no XML output",
            detail=proc.stderr[:4000],
        ))
        return report

    _parse_junit_xml(xml_path, report)
    return report


def _parse_junit_xml(xml_path: str, report: TestReport) -> None:
    """Read a JUnit XML file and populate the TestReport in place."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        report.errored = 1
        report.failures.append(TestFailure(
            name="<parse>", classname="qa.runner",
            duration_s=0.0,
            message=f"JUnit XML parse error: {exc}",
            detail="",
        ))
        return

    root = tree.getroot()
    # pytest's XML can be a single <testsuite> or a <testsuites> wrapper
    suites = (
        [root] if root.tag == "testsuite"
        else list(root.findall("testsuite"))
    )
    for suite in suites:
        report.total    += int(suite.attrib.get("tests",    0))
        report.failed   += int(suite.attrib.get("failures", 0))
        report.errored  += int(suite.attrib.get("errors",   0))
        report.skipped  += int(suite.attrib.get("skipped",  0))
        for case in suite.findall("testcase"):
            failure_node = case.find("failure") or case.find("error")
            if failure_node is not None:
                msg = failure_node.attrib.get("message", "")
                detail = (failure_node.text or "")[:8000]
                report.failures.append(TestFailure(
                    name=case.attrib.get("name", "?"),
                    classname=case.attrib.get("classname", "?"),
                    duration_s=float(case.attrib.get("time", 0.0)),
                    message=msg,
                    detail=detail,
                ))
    report.passed = max(
        0, report.total - report.failed - report.errored - report.skipped,
    )


__all__ = ["TestFailure", "TestReport", "run_tests"]
