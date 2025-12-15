import cv2
from ultralytics import YOLO

def main():
    # Load the YOLOv10 model
    model = YOLO("yolov10n.pt")

    # Open a connection to the default webcam (0)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        if not ret:
            print("Error: Can't receive frame (stream end?). Exiting ...")
            break

        # Run YOLOv10 inference on the frame
        results = model(frame, verbose=False)

        # Draw bounding boxes and labels on the frame
        for r in results:
            for box in r.boxes:
                if box.cls == 0:  # Class for 'person'
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    confidence = box.conf[0]
                    
                    # Draw rectangle
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # Prepare label text
                    label = f"Person: {confidence:.2f}"
                    
                    # Put label on the frame
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Display the resulting frame
        cv2.imshow('YOLOv10 Webcam Test', frame)

        # Break the loop on 'q' key press
        if cv2.waitKey(1) == ord('q'):
            break

    # When everything done, release the capture and destroy windows
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
