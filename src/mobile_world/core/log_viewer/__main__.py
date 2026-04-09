"""Entry point for running log_viewer as a module."""

import sys

from mobile_world.core.log_viewer.app import main

if __name__ == "__main__":
    log_root = sys.argv[1] if len(sys.argv) > 1 else ""
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8760
    main(log_root=log_root, server_port=port)
