# Rubber Tracking System

## Overview
This project is a rubber tracking system designed to process camera input,
track objects, and manage tracking data through a structured workflow.
It integrates externally provided identifiers and maintains consistent tracking state across the system.

## System Architecture
![System Overview](docs/diagrams/overall_system_flow.jpg)

## Core Components

### InformationManager
Manages tracking data (ID, baler, etc.) and validates synchronization.

![InformationManager Flow](docs/diagrams/information_manager_flow.jpg)

### TrackingWorker
Handles the main tracking workflow, and forwards tracking results to other components.

![TrackingWorker Flow](docs/diagrams/tracking_worker_flow.jpg)

## Project Structure
```
configs/
├── base.yaml
├── interfaces/
│ ├── log.yaml
│ ├── receiver.yaml
│ └── video_source.yaml
└── modules/
  └── detect.yaml
  
src/
├── main.py # Application entry point
│
├── classify/ # Classification logic
│ └── classifier.py
│
├── detect/ # Detection pipeline
│ ├── hailo_apps_infra/ # Hailo + GStreamer integration
│ ├── detector.py
│ ├── packet.py
│ ├── frame.py
│ ├── bboxes.py
│ ├── parser.py
│ └── uitils.py
│
├── interfaces/ # External interfaces (video_source, network I/O)
│ ├── video/
│ │ ├── source.py
│ │ └── packet.py
│ ├── receiver/
│ │ ├── receiver.py
│ │ └── packet.py
│ ├── sender/
│ │ ├── sender.py
│ │ └── packet.py
│ └── utils/
│   ├── connection.py
│   ├── tcp_client.py
│   └── tcp_server.py
│
├── rubber_tracking/ # Tracking core modules
│ ├── information_manager.py
│ ├── tracker.py
│ └── tracking_worker.py
│
└── utils/ # Utility modules
  ├── config.py
  ├── inbox.py
  ├── logger.py
  ├── queue.py
  ├── thread.py
  └── common.py
```