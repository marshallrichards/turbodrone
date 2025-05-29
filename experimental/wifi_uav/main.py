import time
import queue
import socket
import threading

import cv2
import numpy as np

from jpeg import generate_jpeg_headers, EOI
from packets import START_STREAM, REQUEST_A, REQUEST_B

# Constants and Configurations
width = 640
height = 360
num_components = 3

# Target IP and port
target_ip = "192.168.169.1"
target_port = 8800
local_port = 56563

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

try:
    sock.bind(("", local_port))
    print(f"Socket bound to port {local_port}")
except socket.error as e:
    print(f"Could not bind socket: {e}")
    sock.close()
    import sys

    sys.exit(f"Terminating: Socket binding failed")


def receive_frames(sock, frame_queue):
    print("Starting frame reception thread...")

    JPEG_HEADER = generate_jpeg_headers(width, height, num_components)
    frame_count = 0

    rqst_A = bytearray(REQUEST_A)
    rqst_B = bytearray(REQUEST_B)

    # Start the video feed
    sock.sendto(START_STREAM, (target_ip, target_port))
    time.sleep(0.1)
    sock.sendto(START_STREAM, (target_ip, target_port))
    time.sleep(0.1)

    while True:
        try:
            print(f"Requesting frame {frame_count}")
            frame_count_bytes = frame_count.to_bytes(2, "little")

            rqst_A[12], rqst_A[13] = frame_count_bytes

            rqst_B[12], rqst_B[13] = frame_count_bytes
            rqst_B[88], rqst_B[89] = frame_count_bytes
            rqst_B[107], rqst_B[108] = frame_count_bytes

            sock.sendto(rqst_A, (target_ip, target_port))
            sock.sendto(rqst_B, (target_ip, target_port))
            frame_count += 1
        except socket.error as e:
            print(f"Error sending data: {e}")
            break

        jpeg_blobs = []
        sock.settimeout(0.5)

        while True:
            try:
                data, _ = sock.recvfrom(1100)

                # In JPEG packets, second byte is 0x01
                if data[1] != 0x01:
                    continue

                # Concatenate JPEG data (without their custom header)
                fragment_index = int.from_bytes(bytes(data[32:34]), "little")
                frame_index = int.from_bytes(bytes(data[16:18]), "little")
                # If the packet is not from the frame we have requested, skip
                if frame_index != frame_count:
                    continue
                # Store the fragment index and the JPEG blobs to order them
                jpeg_blobs.append((fragment_index, data[56:]))
                # Third byte is 0x38 unless it's the last fragment
                if data[2] != 0x38:
                    print(
                        f"Received {len(jpeg_blobs)} fragments for frame {frame_index}."
                        f"Theoretical length = {fragment_index + 1}."
                    )
                    break
            except socket.timeout:
                print("timeout")
                break
            except socket.error as e:
                print(f"Error receiving frame data: {e}")
                break

        # Order the blobs and concatenate them
        full_frame = bytearray()
        for _, blob in sorted(jpeg_blobs, key=lambda x: x[0]):
            full_frame.extend(blob)

        if full_frame:
            total_bytes = bytearray()
            # Build the JPEG from the data blob
            total_bytes.extend(JPEG_HEADER)
            total_bytes.extend(full_frame)
            total_bytes.extend(EOI)
            try:
                frame_queue.put(total_bytes, block=False)
            except queue.Full:
                pass

        time.sleep(0.02)


def calculate_fps(start_time, frame_count):
    elapsed = time.time() - start_time
    return frame_count / elapsed if elapsed > 0 else 0


def process_frame(frame_queue):
    print("Starting frame processing thread...")

    fps_start_time = time.time()
    fps_frame_count = 0

    while True:
        try:
            jpeg_data = frame_queue.get(timeout=1)
            np_buffer = np.frombuffer(jpeg_data, np.uint8)
            frame = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)

            if frame is not None:
                smoothed = cv2.GaussianBlur(frame, (5, 5), 0)
                cv2.imshow("Frame", smoothed)

                fps_frame_count += 1
                if fps_frame_count >= 30:
                    fps = calculate_fps(fps_start_time, fps_frame_count)
                    print(f"FPS: {fps:.2f}")
                    fps_frame_count = 0
                    fps_start_time = time.time()
            else:
                print("Failed to decode frame.")

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        except queue.Empty:
            print("passing")
            pass
        except Exception as e:
            print(f"Error processing frame: {e}")


if __name__ == "__main__":
    frame_queue = queue.Queue(maxsize=100)
    receiver_thread = threading.Thread(target=receive_frames, args=(sock, frame_queue))
    processor_thread = threading.Thread(target=process_frame, args=(frame_queue,))
    receiver_thread.daemon = True
    processor_thread.daemon = True
    receiver_thread.start()
    processor_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Terminating...")
    finally:
        sock.close()
        cv2.destroyAllWindows()
        print("Clean up complete.")
