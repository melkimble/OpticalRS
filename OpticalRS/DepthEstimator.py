# -*- coding: utf-8 -*-
"""
DepthEstimator
==============

Code for handling required data and producing depth estimates from multispectral
satellite imagery.
"""

from RasterDS import RasterDS
from ArrayUtils import mask3D_with_2D
import KNNDepth
import numpy as np
from sklearn.cross_validation import train_test_split

class DepthEstimator(object):
    """
    I want to be able to chuck in the image and the known depths in a number of
    different formats and do depth prediction stuff with it.

    Assumptions:
    - size of known_depths array = size of a single band of img
    - unmasked known_depths pixels are a subset of unmasked img pixels
    """
    def __init__(self,img,known_depths,k=5,weights='uniform'):
        self.img_original = img
        self.imrds = None
        try:
            self.imlevel = img.ndim
        except AttributeError:
            if type(img).__name__ == 'RasterDS':
                self.imlevel = 4
                self.imrds = img
            else:
                # next line should raise exception if `img` can't make RasterDS
                self.imrds = RasterDS(img)
                self.imlevel = 4
        self.known_original = known_depths
        if type(self.known_original).__name__=='RasterDS':
            self.kdrds = known_depths
        elif np.ma.isMaskedArray(self.known_original):
            self.kdrds = None
        else:
            self.kdrds = RasterDS(self.known_original)
        self.known_depth_arr = None
        self.known_depth_arr = self.__known_depth_arr()
        self.k = k
        self.weights = weights
        self.imarr = self.__imarr()
        self.nbands = self.imarr_flat.shape[-1]

        # Check that the numbers of pixels are compatible
        impix = self.imarr_flat.size / self.nbands
        dpix = self.known_depth_arr_flat.size
        errstr = "{} image pixels and {} depth pixels. Need the same number of pixels."
        assert impix == dpix, errstr.format(impix,dpix)

    def __imarr(self):
        """
        Return 3D (R,C,nBands) image array if possible. If only 2D
        (pixels,nBands) array is available, return `None`.
        """
        try:
            self.imarr
        except AttributeError:
            if self.imlevel == 4:
                self.imarr = self.imrds.band_array
            elif self.imlevel == 3:
                self.imarr = self.img_original
            else: # level 2
                self.imarr = None
        return self.imarr

    def __known_depth_arr(self):
        """
        Return a 2D (R,C) masked array of known depths if possible. If flat
        array was handed in instead, return `None`.
        """
        if self.known_depth_arr:
            pass
        elif self.kdrds:
            arr = self.kdrds.band_array.squeeze()
            self.known_depth_arr = np.ma.masked_invalid(arr)
        elif isinstance(self.known_original,np.ndarray):
            arr = self.known_original.squeeze()
            if arr.ndim > 1:
                self.known_depth_arr = np.ma.masked_invalid(arr)
            else:
                self.known_depth_arr = None
        else:
            # I can't think of a case where we'd get here but...
            self.known_depth_arr = None
        return self.known_depth_arr

    @property
    def known_depth_arr_flat(self):
        if np.ma.isMA(self.known_depth_arr):
            return self.known_depth_arr.ravel()
        else:
            return self.known_original

    @property
    def imarr_flat(self):
        """
        Return all the image pixels in (pixels,bands) shape.
        """
        if self.imlevel > 2:
            return self.imarr.reshape(-1,self.imarr.shape[-1])
        else:
            return self.img_original

    @property
    def known_imarr(self):
        """
        Return 3D (R,C,nBands) image array with pixels masked where no known
        depth is available. If no 3D image array is available, return `None`.
        """
        if np.ma.isMA(self.imarr) and np.ma.isMA(self.known_depth_arr):
            return mask3D_with_2D(self.imarr,self.known_depth_arr.mask)
        else:
            return None

    @property
    def known_imarr_flat(self):
        """
        The flattend (pix,bands) image array with all pixels of unknown depth
        masked.
        """
        if np.ma.isMA(self.known_imarr):
            return self.known_imarr.reshape(-1,self.nbands)
        else:
            mask1b = self.known_depth_arr_flat.mask
            mask = np.repeat(np.atleast_2d(mask1b).T,self.nbands,1)
            return np.ma.masked_where(mask,self.imarr_flat)

    def training_split(self,train_size=0.4,random_state=0):
        """
        Split your `DepthEstimator` into training and test subsets. This is a
        wrapper on the scikit-learn `cross_validation.train_test_split`. More
        info: http://scikit-learn.org/stable/modules/generated/sklearn.cross_validation.train_test_split.html

        Parameters
        ----------
        train_size : float, int, or None (default is 0.4)
            If float, should be between 0.0 and 1.0 and represent the
            proportion of the dataset to include in the train split. If int,
            represents the absolute number of train samples. If None, the value
            is automatically set to 0.75.
        random_state : int or RandomState
            Pseudo-random number generator state used for random sampling.

        Returns
        -------
        (train_DE,test_DE) : tuple of DepthEstimators
            Two `DepthEstimator` objects made with compressed and flattened
            arrays. Suitable for training and/or testing depth estimators but
            not for producing images.
        """
        im_train, im_test, dep_train, dep_test = train_test_split(
                        self.known_imarr_flat, self.known_depth_arr_flat,
                        train_size=train_size,random_state=random_state)
        return DepthEstimator(im_train,dep_train),DepthEstimator(im_test,dep_test)

    def knn_depth_model(self,k=5,weights='uniform'):
        """
        Return a trained KNN depth model. See `OpticalRS.KNNDepth.train_model`
        for more information. This is really just a wrapper over the
        KNeighborsRegressor model in scikit-learn.
        """
        return KNNDepth.train_model(self.known_imarr_flat.compressed().reshape(-1,self.nbands),
                                    self.known_depth_arr_flat.compressed(),
                                    k=k,weights=weights)
