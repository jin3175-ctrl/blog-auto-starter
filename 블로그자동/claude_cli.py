"""claude -p (구독 요금제, 헤드리스) 공용 호출 헬퍼."""
from __future__ import annotations

import subprocess


class NotLoggedInError(RuntimeError):
    """claude CLI가 구독 로그인되어 있지 않을 때."""


def run_claude_p(prompt: str, timeout: int = 300) -> str:
    """`claude -p` 로 프롬프트를 실행하고 텍스트 결과를 반환.

    구독 로그인이 안 돼 있으면 NotLoggedInError 발생.
    """
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, timeout=timeout,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "Not logged in" in combined or "Please run /login" in combined:
        raise NotLoggedInError(
            "claude CLI가 구독 로그인되어 있지 않습니다. 터미널에서 `claude login` 을 한 번 실행해 "
            "구독(Max/Pro) 계정으로 로그인한 뒤 다시 시도하세요. (-p 방식은 로그인된 구독을 사용합니다)"
        )
    out = proc.stdout.strip()
    if proc.returncode != 0 and not out:
        raise RuntimeError(
            f"claude -p 실패 (code {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    if not out:
        raise RuntimeError("claude -p 가 빈 결과를 반환했습니다.")
    return out
