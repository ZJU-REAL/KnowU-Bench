import io
import subprocess
import threading
import time

import gradio as gr
from PIL import Image


class ScrcpyScreenViewer:
    def __init__(self):
        self.scrcpy_process = None
        self.screenshot_thread = None
        self.is_streaming = False
        self.current_image = None
        self.device_id = None

    def get_connected_devices(self):
        """Get list of connected Android devices/emulators"""
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            devices = []
            for line in result.stdout.split("\n")[1:]:
                if "\tdevice" in line:
                    device_id = line.split("\t")[0]
                    devices.append(device_id)
            return devices
        except Exception as e:
            print(f"Error getting devices: {e}")
            return []

    def take_screenshot(self, device_id=None):
        """Take a screenshot using ADB"""
        try:
            cmd = ["adb"]
            if device_id:
                cmd.extend(["-s", device_id])
            cmd.extend(["exec-out", "screencap", "-p"])

            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0:
                image = Image.open(io.BytesIO(result.stdout))
                return image
            return None
        except Exception as e:
            print(f"Screenshot error: {e}")
            return None

    def start_streaming(self, device_id, fps=2):
        """Start continuous screenshot streaming"""
        if self.is_streaming:
            self.stop_streaming()

        self.device_id = device_id
        self.is_streaming = True
        interval = 1.0 / fps

        def screenshot_worker():
            while self.is_streaming:
                try:
                    screenshot = self.take_screenshot(device_id)
                    if screenshot:
                        # Resize for better web display
                        screenshot.thumbnail((800, 1200), Image.Resampling.LANCZOS)
                        self.current_image = screenshot
                    time.sleep(interval)
                except Exception as e:
                    print(f"Screenshot loop error: {e}")
                    time.sleep(1)

        self.screenshot_thread = threading.Thread(target=screenshot_worker, daemon=True)
        self.screenshot_thread.start()

        return "🟢 Screen streaming started"

    def stop_streaming(self):
        """Stop screenshot streaming"""
        self.is_streaming = False
        self.current_image = None
        return "🔴 Screen streaming stopped"

    def get_current_screenshot(self):
        """Get the current screenshot"""
        return self.current_image


# Initialize the viewer
viewer = ScrcpyScreenViewer()


# Gradio interface functions
def refresh_devices():
    """Refresh the list of available devices"""
    devices = viewer.get_connected_devices()
    if devices:
        return gr.Dropdown(choices=devices, value=devices[0])
    else:
        return gr.Dropdown(choices=[], value=None)


def start_screen_stream(device_id, fps):
    """Start streaming the device screen"""
    if not device_id:
        return "❌ Error: No device selected", None

    message = viewer.start_streaming(device_id, fps)
    return message, viewer.current_image


def stop_screen_stream():
    """Stop streaming the device screen"""
    message = viewer.stop_streaming()
    return message, None


def get_screen_update():
    """Get current screen for auto-refresh"""
    return viewer.current_image


# Create the Gradio interface
with gr.Blocks(title="Android Screen Viewer", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📱 Android Emulator Screen Viewer")
    gr.Markdown(
        "View your Android emulator or device screen in real-time through your web browser."
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🔧 Device Settings")

            device_dropdown = gr.Dropdown(
                label="📱 Select Device/Emulator",
                choices=viewer.get_connected_devices(),
                value=viewer.get_connected_devices()[0] if viewer.get_connected_devices() else None,
                info="Choose your Android device or emulator",
            )

            fps_slider = gr.Slider(
                minimum=0.5,
                maximum=5,
                value=1,
                step=0.5,
                label="🎯 Refresh Rate (FPS)",
                info="Higher values = smoother but more resource intensive",
                visible=False,
            )

            with gr.Row():
                refresh_devices_btn = gr.Button("🔄 Refresh Devices", size="sm")
                start_btn = gr.Button("▶️ Start Viewing", variant="primary", size="sm")
                stop_btn = gr.Button("⏹️ Stop Viewing", variant="stop", size="sm")

            status_text = gr.Textbox(
                label="📊 Status", value="Ready to connect", interactive=False, lines=2
            )

            # Device info section
            # gr.Markdown("### 📋 Instructions")
            # gr.Markdown("""
            # 1. **Connect** your Android device or start an emulator
            # 2. **Enable USB Debugging** in Developer Options
            # 3. **Select device** from the dropdown above
            # 4. **Click "Start Viewing"** to begin screen streaming
            # 5. **Adjust FPS** for smoother or more efficient viewing
            # """)

        with gr.Column(scale=2):
            gr.Markdown("### 📺 Device Screen")

            screen_image = gr.Image(
                label="Live Screen View",
                type="pil",
                height=700,
                show_label=False,
                container=True,
                show_download_button=True,
            )

            with gr.Row():
                manual_refresh_btn = gr.Button("🔄 Manual Refresh", size="sm")
                screenshot_btn = gr.Button("📸 Take Screenshot", size="sm")

    # Event handlers
    refresh_devices_btn.click(refresh_devices, outputs=[device_dropdown])

    start_btn.click(
        start_screen_stream,
        inputs=[device_dropdown, fps_slider],
        outputs=[status_text, screen_image],
    )

    stop_btn.click(stop_screen_stream, outputs=[status_text, screen_image])

    manual_refresh_btn.click(get_screen_update, outputs=[screen_image])

    screenshot_btn.click(
        lambda device_id: viewer.take_screenshot(device_id),
        inputs=[device_dropdown],
        outputs=[screen_image],
    )

    # Auto-refresh functionality
    def create_auto_refresh():
        while True:
            time.sleep(0.5)  # Check every 500ms
            if viewer.is_streaming:
                yield viewer.current_image
            else:
                yield gr.skip()

    # Set up auto-refresh when the page loads
    app.load(refresh_devices, outputs=[device_dropdown])

    # Auto-update the screen image every second when streaming
    screen_refresh = gr.Timer(value=1.0)  # Refresh every 1 second
    screen_refresh.tick(get_screen_update, outputs=[screen_image])


# Cleanup function
def cleanup():
    viewer.stop_streaming()


if __name__ == "__main__":
    try:
        print("🚀 Starting Android Screen Viewer...")
        print("📱 Make sure your Android device/emulator is connected and USB debugging is enabled")
        print("🌐 Opening web interface...")

        app.launch(share=False, server_name="0.0.0.0", show_error=True, quiet=False)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        cleanup()
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        cleanup()
