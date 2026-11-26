"""Initialize/restore/verify a team DB; legacy export is disabled for security.

Restore needs psycopg and DATABASE_URL; run init ONLY on the team DB.
Bundles contain source data: review access, secrets and licensing before sharing.
"""
import argparse
import sys
if __package__:
    from . import store
else:
    import store

def legacy(container, chunks_path, expected):
    """Legacy source export is disabled, including direct calls."""
    raise RuntimeError('legacy-export disabled; do not retry automatically')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('legacy-export', help='disabled for security')
    p.add_argument('--container', required=True)
    p.add_argument('--chunks', required=True, help='original complete chunks JSONL')
    p.add_argument('--output', required=True, help='new private bundle file, never overwrite')
    p.add_argument('--expected-count', type=int, default=1504)
    p = sub.add_parser('init', help='create new schema on DATABASE_URL; requires public.vector')
    p.add_argument('--confirm-target', required=True, help='exact target database name')
    p.add_argument('--allow-remote-target', action='store_true')
    for name in ('restore', 'verify'):
        p = sub.add_parser(name)
        p.add_argument('--bundle', required=True)
        if name == 'restore':
            p.add_argument('--confirm-target', required=True, help='exact target database name')
            p.add_argument('--allow-remote-target', action='store_true')
    args = parser.parse_args()
    committed = False
    commit_unknown = False
    identity = None
    try:
        if args.action == 'legacy-export':
            # Until private creation and path containment can be established
            # atomically, do not read the source or create an output at all.
            print('legacy-export disabled: private output security is not verified; '
                  'do not retry automatically', file=sys.stderr)
            return 1
        elif args.action == 'init':
            with store.connect() as conn:
                try:
                    identity = store.init(conn, args.confirm_target, args.allow_remote_target)
                except store.CommitOutcomeUnknown:
                    commit_unknown = True
                    raise
                committed = True
            with store.connect() as conn:
                if store.check_target(conn, args.confirm_target, args.allow_remote_target) != identity:
                    raise ValueError('readback target differs from init target')
                store.verify_init(conn)
            print('schema created and verified')
        else:
            obj = store.read_bundle(args.bundle)
            with store.connect() as conn:
                if args.action == 'restore':
                    try:
                        identity = store.restore(conn, obj, args.confirm_target, args.allow_remote_target)
                    except store.CommitOutcomeUnknown:
                        commit_unknown = True
                        raise
                    committed = True
                else:
                    store.verify(conn.cursor(), obj)
            if args.action == 'restore':
                with store.connect() as conn:
                    if store.check_target(conn, args.confirm_target, args.allow_remote_target) != identity:
                        raise ValueError('readback target differs from restore target')
                    store.verify(conn.cursor(), obj)
            print(args.action, 'verified:', len(obj['records']), 'rows')
        return 0
    except Exception:
        if committed:
            print('committed_readback_unknown: do not retry automatically; inspect the target', file=sys.stderr)
        elif commit_unknown:
            print('commit_unknown: do not retry automatically; inspect the target database state', file=sys.stderr)
        else:
            print('operation failed; inspect target and inputs safely; details suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
