from ximea import xiapi
import cv2
import numpy as np
from scipy import misc
import time

#create instance for first connected camera 
cam = xiapi.Camera()

#start communication
print('Opening first camera...')
cam.open_device()

#settings
cam.set_imgdataformat('XI_MONO8')
cam.set_exposure(20000)

#create instance of Image to store image data and metadata
img = xiapi.Image()

#start data acquisition
print('Starting data acquisition...')
cam.start_acquisition()

#get data and pass them from camera to img
cam.get_image(img)

#create numpy array with data from camera. Dimensions of array are determined
#by imgdataformat
data = img.get_image_data_numpy()

# save image
# image = (data.copy() / 65535 * 255).astype('uint8')
image = data.astype('uint8')
cv2.imwrite("../images/{}.jpg".\
    format(time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())), image)

#stop data acquisition
print('Stopping acquisition...')
cam.stop_acquisition()

#stop communication
cam.close_device()

#show acquired image
print('Drawing image...')
cv2.imshow('XiCAM example', 20*data)
cv2.waitKey(0)
cv2.destroyAllWindows()

print('Done.')
