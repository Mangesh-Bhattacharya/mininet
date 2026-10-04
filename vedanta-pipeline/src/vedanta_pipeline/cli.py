from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .orchestrator import Pipeline


def _publisher(cfg, args):
    if cfg.publish_mode != "schedule" and not getattr(args, "interactive", False):
        return None
    from .publish.youtube import YouTubePublisher
    p = YouTubePublisher(cfg, Path(args.client_secret), Path(args.token))
    p.authorize(interactive=getattr(args, "interactive", False))
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vedanta")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--client-secret", default="secrets/client_secret.json")
    ap.add_argument("--token", default="secrets/token.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once", help="run one pipeline tick")
    sub.add_parser("run", help="run 24x7 loop")
    sub.add_parser("status", help="print status.json")
    sub.add_parser("verify-audit", help="verify audit-log hash chain")
    a = sub.add_parser("auth", help="one-time interactive YouTube OAuth")
    a.set_defaults(interactive=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    if args.cmd == "status":
        print((cfg.state_dir / "status.json").read_text())
        return 0
    if args.cmd == "auth":
        _publisher(cfg, args)
        print("token saved (0600)")
        return 0
    pipe = Pipeline(cfg, _publisher(cfg, args), autocomplete=True)
    if args.cmd == "verify-audit":
        ok = pipe.audit.verify()
        print("audit chain OK" if ok else "AUDIT CHAIN BROKEN")
        return 0 if ok else 2
    if args.cmd == "once":
        print(pipe.run_once())
    else:
        pipe.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
