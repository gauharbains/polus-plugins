import os
import cv2
import numpy as np
from aicsimageio import AICSImage
from scipy.ndimage.morphology import binary_fill_holes
from aicssegmentation.core.seg_dot import dot_2d_slice_by_slice_wrapper
from aicssegmentation.core.pre_processing_utils import intensity_normalization, image_smoothing_gaussian_3d
from skimage.morphology import remove_small_objects, binary_closing, ball, disk, erosion, dilation   # function for post-processing (size filter)
from aicssegmentation.core.MO_threshold import MO


def segment_images(inpDir, outDir, config_data):  

    inpDir_files = os.listdir(inpDir)
    for i,f in enumerate(inpDir_files):
        # Load an image
        #br = BioReader(Path(inpDir).joinpath(f))
        #image = np.squeeze(br.read_image())
        
        reader = AICSImage(os.path.join(inpDir,f)) 
        image = reader.data.astype(np.float32)
            
        structure_channel = 0
        struct_img0 = image[0,structure_channel,:,:,:].copy()

        intensity_scaling_param = config_data['intensity_scaling_param']
        struct_img = intensity_normalization(struct_img0, scaling_param=intensity_scaling_param) 

        gaussian_smoothing_sigma = config_data['gaussian_smoothing_sigma'] 
        structure_img_smooth = image_smoothing_gaussian_3d(struct_img, sigma=gaussian_smoothing_sigma)

        global_thresh_method = config_data['global_thresh_method'] 
        object_minArea = config_data['object_minArea'] 
        bw, object_for_debug = MO(structure_img_smooth, global_thresh_method=global_thresh_method, object_minArea=object_minArea, return_object=True)

        s2_param_bright = config_data['s2_param_bright']
        s2_param_dark = config_data['s2_param_dark']

        bw_extra = dot_2d_slice_by_slice_wrapper(structure_img_smooth, s2_param_bright)
        bw_dark = dot_2d_slice_by_slice_wrapper(1-structure_img_smooth, s2_param_dark)

        bw_merge = np.logical_or(bw, bw_extra)
        bw_merge[bw_dark>0]=0

        minArea = config_data['minArea']
        seg = remove_small_objects(bw_merge>0, min_size=minArea, connectivity=1, in_place=False)

        seg = seg > 0
        out=seg.astype(np.uint8)
        out[out>0]=255
        cv2.imwrite(os.path.join(outDir,f), out[0,:,:])