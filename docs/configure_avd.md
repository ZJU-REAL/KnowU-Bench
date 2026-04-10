Tutorial on how to configure the AVD in Android Studio.

1. Make sure you are within the `mobile_world` repo directory and run `sudo mobile-world env run --image mobile_world:v1.1 --dev` will launch a dev container with the existing AVD image. This dev container will have your local `src` mounted to `/app/service/src`.
2. Run `sudo mobile-world env exec knowu_bench_env_0_dev` to enter the dev container.
3. Run `adb emu avd snapshot load init_state` to load the initial snapshot of the AVD.
4. Go to the VNC page (you will see the address to this page at step 1) to see the interactive Android Emulator.
5. Manually configure the environment (e.g., install apps, push new files, etc.).
6. Once you are done:
    - first run `adb shell su root date 101612002025.00` to set the date to our fixed date (2025-10-16 12:00:00).
    - run `adb emu avd snapshot save init_state` to overwrite the initial snapshot. This snapshot will be loaded for tasks by default.
    - run `adb emu kill` to kill the emulator.
7. Exit the dev container and copy the AVD folder to the `docker/` folder via `sudo docker cp knowu_bench_env_0_dev:/root/.android/avd/Pixel_8_API_34_x86_64.avd docker/`.
8. Compile a new image with the new AVD folder via `sudo docker buildx build -t mobile_world:v1.2 -f docker/Dockerfile .`.