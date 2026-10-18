"""Stable local entry point: reuse a healthy service or start it, then open."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler
import webbrowser

HERE = Path(__file__).resolve().parent


def live_connection(base):
    try:
        connection = json.loads((base / '.data' / 'connection.json').read_text(encoding='utf-8-sig'))
        url, token = connection['url'], connection['token']
        if not isinstance(url, str) or not re.fullmatch(r'http://127\.0\.0\.1:[1-9]\d{0,4}', url):
            return None
        if not isinstance(token, str) or not token or len(token) > 256:
            return None
        request = Request(url + '/api/data', headers={'X-Skill-Ledger-Token': token})
        # Loopback must not be sent to a system proxy or follow redirects.
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=1) as response:
            value = json.load(response)
        if not isinstance(value.get('skills'), list) or not isinstance(value.get('events'), list):
            return None
        return connection
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def start_monitor(base):
    runtime = Path(sys.executable)
    if os.name == 'nt' and runtime.with_name('pythonw.exe').is_file():
        runtime = runtime.with_name('pythonw.exe')
    return subprocess.Popen(
        [str(runtime), str(HERE / 'skill_ledger.py'), '--base', str(base), '--watch', '--quiet'],
        cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )


def open_ledger(base, timeout=25):
    base = Path(base).resolve()
    connection = live_connection(base)
    reused = connection is not None
    if connection is None:
        start_monitor(base)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(.25)
            connection = live_connection(base)
            if connection:
                break
    if not connection:
        raise RuntimeError('后台尚未就绪，请查看台账目录下 .data/运行错误.log 后重试。')
    from urllib.parse import quote
    if not webbrowser.open(connection['url'] + '/#access=' + quote(connection['token'], safe='')):
        raise RuntimeError('无法打开系统默认浏览器，请检查默认浏览器设置后重试。')
    return reused


def main():
    parser = argparse.ArgumentParser(description='在默认浏览器打开技能台账，必要时启动后台。')
    parser.add_argument('--base', type=Path, default=HERE)
    args = parser.parse_args()
    try:
        open_ledger(args.base)
    except Exception as error:
        message = str(error)
        if sys.stderr:
            print(message, file=sys.stderr)
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, '技能台账：打开失败', 0x10)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
