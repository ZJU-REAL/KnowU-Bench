"""Device subcommand for MobileWorld CLI - Live Android device screen viewer."""

import argparse
import sys


def configure_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configure the device subcommand parser."""
    device_parser = subparsers.add_parser(
        "device",
        aliases=["viewer"],  # Keep 'viewer' as alias for backward compatibility
        help="View live Android device screen",
    )
    device_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the viewer to (default: 0.0.0.0)",
    )
    device_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for the viewer (default: auto-assign)",
    )


async def execute(args: argparse.Namespace) -> None:
    """Execute the device command."""
    try:
        from mobile_world.core.device_viewer import app as viewer_app

        print("🚀 Starting Android Screen Viewer...")
        print("📱 Make sure your Android device/emulator is connected and USB debugging is enabled")
        print("🌐 Opening web interface...")

        viewer_app.launch(
            server_name=args.host,
            server_port=args.port,
            share=False,
            show_error=True,
            quiet=False,
        )
    except ImportError as e:
        print(f"❌ Error: Could not import device viewer. Make sure gradio is installed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting viewer: {e}")
        sys.exit(1)
