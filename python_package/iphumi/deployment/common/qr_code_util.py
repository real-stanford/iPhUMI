# adapted from Mengda Xu's code

import cv2
import numpy as np
import qrcode
from datetime import datetime
import time

# Function to generate a QR code with encoded monotonic time
def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=8,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")

    # Convert the PIL image to OpenCV format (numpy array)
    open_cv_image = np.array(img.convert("RGB"))
    open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
    return open_cv_image


def display_qr_cv2(img):
    cv2.imshow("QR Code", img)
    cv2.waitKey(1)  # Display for 1 millisecond to allow updating


def dynamic_qr_timecode():
    try:
        while True:
            # Get current time in ISO format
            timecode = datetime.now().isoformat()

            # Generate the QR code with the ISO time as data
            qr_img = generate_qr(timecode)

            # Display the QR code using OpenCV
            display_qr_cv2(qr_img)

            # Wait for 0.02 seconds before generating the next QR code
            time.sleep(1 / 120)

    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        # Close the OpenCV window when done
        cv2.destroyAllWindows()


# Function to read and decode QR codes from an image
def read_qr_code(image):
    # Use cv2 to read QR code in the image
    detector = cv2.QRCodeDetector()
    try:
        qr_data, _, _ = detector.detectAndDecodeCurved(image)
    except:
        return None
    
    if qr_data is not None and qr_data != '':
        return qr_data
    else:
        return None
