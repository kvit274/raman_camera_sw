THIS PROJECT IS STILL IN PROGRESS...

Raman Camera Control & Acquisition Software

This project is a modular desktop application for controlling a Raman spectroscopy camera and managing the full image acquisition pipeline. It provides a clean separation between UI, control logic, and hardware interaction, ensuring responsiveness, reliability, and maintainability.

The software allows users to configure camera parameters such as readout modes, binning, ROI, exposure settings, and cooling control, while handling long-running hardware operations asynchronously to keep the interface responsive. Acquired frames can be previewed in real time and saved to disk for further analysis.

The architecture follows a controller-driven design, where the UI remains passive, the controller coordinates execution flow, and the model interfaces directly with the camera SDK. Background operations (e.g. cooling, acquisition) are executed in dedicated worker threads to avoid blocking the main event loop.

This project is intended for laboratory and research environments where stable camera control, clear execution flow, and extensibility are critical, and serves as a foundation for more advanced Raman data processing and automation workflows.
