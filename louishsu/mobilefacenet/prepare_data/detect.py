import os
import sys
sys.path.append('../')

import cv2
import time
import numpy as np

import torch_mtcnn.detector as mtcnn
from torch_mtcnn.detector import show_bbox

def keep_one(image, boxes_c):
    c = np.array(image.shape[:-1]) / 2
    boxes = boxes_c[:, :-1]
    c_x = (boxes[:, 0] + boxes[:, 2]).reshape(-1, 1) / 2
    c_y = (boxes[:, 1] + boxes[:, 3]).reshape(-1, 1) / 2
    cs = np.c_[c_x, c_y]

    d = np.linalg.norm(cs-c, axis=1)
    idx = np.argmin(d)
    return idx

def detect_casia(prefix='../data/CASIA-WebFace'):
    """
    Notes:
        只保存检测出人脸的文件及其坐标
    """
    print('\033[2J\033[1;1H')

    detector = mtcnn.MtcnnDetector(min_face=24, thresh=[0.8, 0.6, 0.7], scale=0.79, stride=2, cellsize=12)
    fp = open('../data/CASIA_detect.txt', 'w')
    
    i = 0; n = 494414
    elapsed_time = 0
    start_time = time.time()

    for subdir in os.listdir(prefix):
        subdir = os.path.join(prefix, subdir)
        
        for imidx in os.listdir(subdir):
            i += 1
            duration = time.time() - start_time
            elapsed_time += duration
            start_time = time.time()
            
            print('\033[5;1H[{:6d}]/[{:6d}] FPS: {:.4f}  Elapsed: {:.4f}h Left: {:.4f}h'.\
                            format(i, n, 1./duration, elapsed_time/3600, (duration*n - elapsed_time)/3600))
            
            imfile = os.path.join(subdir, imidx)

            img = cv2.imread(imfile, cv2.IMREAD_ANYCOLOR)
            boxes_c, landmark = detector.detect_image(img)
            if boxes_c.shape[0] == 0: continue
            
            idx = keep_one(img, boxes_c)
            b, m = list(boxes_c[idx]), list(landmark[idx])
            line = ' '.join(map(str, b + m))
            line = '/'.join(imfile.split('/')[-2:]) + ' ' + line + '\n'
            fp.write(line)

    fp.close()

if __name__ == "__main__":
    detect_casia()