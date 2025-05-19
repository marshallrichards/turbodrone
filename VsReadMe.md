# TurboDrone Vision System Development Plan

**Project: Real-time Monocular 3D Mapping and Safe Path Planning for Drones**

**Overall Goal:** Enhance the drone system to reconstruct 3D terrain, identify hazards from monocular video, and suggest a safe path, all displayed live.

## Configuration and Environment Setup

### Required Repositories
1. **TurboDrone** (Main Project)
   ```bash
   git clone https://github.com/yourusername/turbodrone.git
   cd turbodrone
   ```

2. **Apple Depth Pro** (Depth Estimation)
   ```bash
   git clone https://github.com/apple/ml-depth-pro.git
   cd ml-depth-pro
   ```

### Environment Setup
1. **Create and activate virtual environment**
   ```bash
   python -m venv depth-pro-env
   source depth-pro-env/bin/activate  # On macOS/Linux
   ```

2. **Install TurboDrone dependencies**
   ```bash
   cd turbodrone
   pip install -r requirements.txt
   pip install ultralytics  # For YOLO object detection
   ```

3. **Install Depth Pro dependencies**
   ```bash
   cd ../ml-depth-pro
   pip install -e .
   ```

4. **Copy model checkpoints**
   ```bash
   # Copy the checkpoint file to the expected location
   cp path/to/checkpoint.pth depth-pro-env/lib/python3.9/site-packages/depth_pro/checkpoints/
   ```

5. **Note on large model files**
   ```bash
   # Large model files like checkpoints/depth_pro.pt (1.8GB) are excluded from Git using .gitignore
   # When setting up a new environment, download these files separately or use Git LFS
   # See previous step for download instructions.
   ```

### Running the System
1. **Activate environment**
   ```bash
   source depth-pro-env/bin/activate
   ```

2. **Start video receiver with depth estimation**
   ```bash
   python src/receive_video.py
   ```

### Current Features
- Real-time video feed from TurboDrone S20
- YOLO object detection
- Depth estimation using Apple Depth Pro
- Multi-threaded processing for performance
- Live visualization of RGB feed and depth maps

## Task Ownership Legend
- 🧑 [USER] - Requires user decision/action
- 🤖 [AI_AGENT] - Can be implemented by AI once dependencies are set up
- 👥 [COLLABORATIVE] - Requires both user input and AI implementation
- ✅ [DONE] - Completed task
- 🔄 [IN_PROGRESS] - Currently being worked on

---

**Phase 1: Core Vision Modules (Individual Components)**

*   **Task 1.1: Setup Monocular Depth Estimation** 🔄 [IN_PROGRESS]
    *   **Goal:** Get a depth map from a single RGB frame.
    *   **Action:**
        1.  ✅ [DONE] Choose a model: Selected Apple's Depth Pro for optimal macOS/Apple Silicon performance
        2.  ✅ [DONE] Install dependencies:
            * Python 3.9 virtual environment
            * Depth Pro package and dependencies
        3.  ✅ [DONE] Download pre-trained model weights
        4.  ✅ [DONE] Integration tasks:
            *   Created wrapper class for video frame processing (DepthEstimator)
            *   Implemented frame preprocessing pipeline
            *   Setup efficient inference loop with threading
            *   Added depth map post-processing and visualization
            *   Configured output format for downstream tasks
        5.  ✅ [DONE] Test and verify visualization with drone camera feed:
            *   Integrated with receive_video.py
            *   Added real-time depth visualization window
            *   Implemented YOLO object detection alongside depth estimation
            *   Added FPS monitoring and display
    *   **Next Steps:**
        1. 🔄 [IN_PROGRESS] Optimize performance:
           * Fine-tune frame sizes and processing pipeline
           * Improve error handling for corrupt frames
           * Add frame dropping for real-time performance
        2. Move to Task 1.2: Point Cloud Generation
    *   **Deliverable:** A robust module that can process video frames in real-time and output depth maps.

*   **Task 1.2: Basic 3D Point Cloud Generation (Single Frame)**
    *   **Goal:** Create a 3D point cloud from an RGB frame and its depth map.
    *   **Action:**
        1.  🧑 [USER] Install Open3D.
        2.  🤖 [AI_AGENT] Write a Python script/function:
            *   Input: An RGB frame and its corresponding depth map (from Task 1.1).
            *   Processing:
                *   Use camera intrinsic parameters (will get from user).
                *   Create Open3D objects and point cloud.
            *   Output: An Open3D `PointCloud` object.
        3.  👥 [COLLABORATIVE] Test and verify visualization.
    *   **Deliverable:** A script that takes an RGB image and depth map to visualize the 3D point cloud.

*   **Task 1.3: Setup Terrain Segmentation**
    *   **Goal:** Classify pixels in a frame into basic terrain types.
    *   **Action:**
        1.  🧑 [USER] Choose a model: DeepLabV3 or SegFormer.
        2.  🧑 [USER] Install necessary libraries.
        3.  🧑 [USER] Download pre-trained model weights.
        4.  🤖 [AI_AGENT] Write a Python script/function:
            *   Input: A single video frame.
            *   Processing:
                *   Preprocess the frame.
                *   Run inference.
                *   Post-process output for hazard classification.
            *   Output: A 2D hazard map.
        5.  👥 [COLLABORATIVE] Test and verify visualization.
    *   **Deliverable:** A script that can load an image and output/display its hazard classification map.

**Phase 2: Dynamic Processing and Integration Preliminaries**

*   **Task 2.1: Rudimentary Pseudo-Pose Estimation**
    *   **Goal:** Estimate camera motion between consecutive frames.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement feature-based matching using OpenCV:
            *   Input: Previous frame, current frame.
            *   Processing:
                *   Feature detection and matching.
                *   Essential matrix estimation.
                *   Pose recovery.
            *   Output: Relative rotation matrix and translation vector.
        2.  👥 [COLLABORATIVE] Test and verify with video sequences.
    *   **Deliverable:** A function that outputs relative transformation between frames.

*   **Task 2.2: Point Cloud Accumulation**
    *   **Goal:** Combine point clouds from multiple frames using estimated poses.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement point cloud accumulation logic.
        2.  👥 [COLLABORATIVE] Test with video sequences.
    *   **Deliverable:** A script that processes video sequences into accumulated point clouds.

**Phase 3: Path Planning and UI**

*   **Task 3.1: Cost Map Generation**
    *   **Goal:** Create a 2D grid representing traversal cost.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement cost map generation function.
        2.  👥 [COLLABORATIVE] Test and verify visualization.
    *   **Deliverable:** A function that produces cost maps from hazard and depth maps.

*   **Task 3.2: A* Path Planner Implementation**
    *   **Goal:** Find the shortest safe path on the cost map.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement A* pathfinding algorithm.
        2.  👥 [COLLABORATIVE] Test with various scenarios.
    *   **Deliverable:** An A* implementation for cost map navigation.

*   **Task 3.3: Overlay Path on Video Frame**
    *   **Goal:** Draw the recommended path onto the displayed video.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement path visualization function.
        2.  👥 [COLLABORATIVE] Test and verify visualization.
    *   **Deliverable:** A function to draw paths on images.

**Phase 4: Modularization and Integration**

*   **Task 4.1: Create `vision_module.py`**
    *   **Goal:** Encapsulate all functionalities into a reusable module.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement the `TerrainMapper` class.
        2.  👥 [COLLABORATIVE] Test and verify all components.
    *   **Deliverable:** A complete Python module for terrain mapping.

*   **Task 4.2: Integrate into `receive_video.py`**
    *   **Goal:** Use the vision module in the video receiving script.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement integration logic.
        2.  👥 [COLLABORATIVE] Test and verify full system.
    *   **Deliverable:** Updated video processing script with terrain mapping.

*   **Task 4.3: Integrate 3D Point Cloud Accumulation (Optional)**
    *   **Goal:** Show live, accumulating 3D map.
    *   **Action:**
        1.  🤖 [AI_AGENT] Implement visualization logic.
        2.  👥 [COLLABORATIVE] Test and verify 3D visualization.
    *   **Deliverable:** Live 3D reconstruction alongside 2D video feed.

## Initial Setup Tasks for User

🧑 [USER] Before we begin implementation:
1. Choose and install the depth estimation model (MiDaS/DPT)
2. Choose and install the segmentation model (DeepLabV3/SegFormer)
3. Install core dependencies:
   - PyTorch
   - OpenCV
   - Open3D
   - Required model-specific libraries
4. Download necessary pre-trained weights
5. Provide camera intrinsic parameters for your setup

Once these are complete, we can begin implementing the AI_AGENT tasks in sequence.

---

**General Advice for the AI Curosr Agent Developer:**

*   **Start Simple:** For each task, get a very basic version working first, then add complexity.
*   **Test Incrementally:** Test each function and small piece of logic as you write it. Use dummy data or simple inputs.
*   **Version Control:** Use Git. Commit often with clear messages (`git add .`, `git commit -m "Implemented basic depth estimation"`).
*   **Read Documentation:** For libraries like OpenCV, PyTorch, Open3D, refer to their official documentationby utilizing your search web feature to find examples.
*   **Manage Dependencies:** Use a `requirements.txt` file or a virtual environment (e.g., `venv` ) to keep track of Python packages and their versions.
*   **Focus on One Thing at a Time:** Don't try to build everything at once. Follow the phased approach.
*   **Performance Later:** Get it working correctly first, then optimize for speed if necessary. The threading in Task 4.2 is the first step towards handling performance.
*   **Error Handling:** Initially, focus on the happy path. Add more robust error handling later (e.g., what if model loading fails? What if no features are matched?).

