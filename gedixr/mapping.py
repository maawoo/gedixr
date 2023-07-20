import datetime
import itertools
import os

import numpy as np
import xarray as xr


class CoordinateMapping:
    """
    Class to map coordinates to a grid

    Parameters
    ----------
    x_start : int
        x coordinate of the lower left corner of the grid
    dim_2_start : int
        y coordinate of the lower left corner of the grid
    dim_1_len : int
        length of the grid in x direction
    dim_2_len : int
        length of the grid in y direction
    resolution : int
        resolution of the grid
    y_resolution : int, optional
        resolution of the grid in y direction, if not given, the x resolution is used

    Attributes
    ----------
    mapping : numpy.ndarray
        mapping of the coordinates to the grid
    dim_1_start : int
        x coordinate of the lower left corner of the grid
    dim_2_start : int
        y coordinate of the lower left corner of the grid
    resolution : int
        resolution of the grid
    dim_2_resolution : int
        resolution of the grid in y direction

    Methods
    -------
    get_mapping_by_index(x, y)
        get the mapping by index
    get_mapping_by_input_coord(x, y)
        get the mapping by coordinate of the input coordinates
    get_mapping_by_coord_point(x, y)
        get the mapping by coordinate of the center of the pixel (shifted by half the resolution in x and y)

    Examples
    --------
    >>> m = CoordinateMapping(dim_1_start=2, dim_2_start=0, dim_1_len=4, dim_2_len=2, resolution=1)
    >>> m.mapping
    array([[0, 1],
           [2, 3],
           [4, 5],
           [6, 7]])
    >>> m.mapping_area()
    array([[[2, 0],
            [3, 0],
            [4, 0],
            [5, 0]],
    <BLANKLINE>
           [[2, 1],
            [3, 1],
            [4, 1],
            [5, 1]]])
    >>> m.mapping_point()
    array([[[2.5, 0.5],
            [3.5, 0.5],
            [4.5, 0.5],
            [5.5, 0.5]],
    <BLANKLINE>
           [[2.5, 1.5],
            [3.5, 1.5],
            [4.5, 1.5],
            [5.5, 1.5]]])
    >>> m.get_mapping_index(2, 1)
    5
    >>> m.get_mapping_by_input_coord(2, 0)
    0
    >>> m.get_mapping_coord_point(2.5, 0.5)
    0
    >>> m.revert_mapping(5)
    (2, 1)
    >>> m.revert_mapping(0)
    (0, 0)

    >>> mapping = CoordinateMapping(dim_1_start=10, dim_2_start=5, dim_1_len=10, dim_2_len=11, \
                                    resolution=1, dim_2_resolution=2)
    >>> mapping.get_mapping_index(0, 0)
    0
    >>> mapping.get_mapping_index(9, 5)
    104
    >>> mapping.revert_mapping(0)
    (0, 0)
    >>> mapping.revert_mapping(104)
    (9, 5)
    >>> mapping.get_mapping_by_input_coord(10, 5)
    0
    >>> mapping.get_mapping_by_input_coord(11, 5)
    11
    >>> mapping.get_mapping_coord_point(10.5, 8)
    1
    >>> mapping.get_mapping_coord_point(19.5, 15)
    103
    """
    
    def __init__(self, xr_dim_1=None, xr_dim_2=None,
                 dim_1_start=None, dim_2_start=None, dim_1_len=None, dim_2_len=None, resolution=None,
                 dim_2_resolution=None):
        
        self.dim_names = [None, None]
        self.mapping = None
        self.map_shape = None
        self.dim_1_start = None
        self.dim_1 = None
        self.dim_2_start = None
        self.dim_2 = None
        self.resolution = None
        self.dim_2_resolution = None
        if xr_dim_1 is not None and xr_dim_2 is not None:
            self.dim_names = [xr_dim_1.name, xr_dim_2.name]
            self.dim_1 = xr_dim_1.values
            self.dim_2 = xr_dim_2.values
            self.dim_1_start = self.dim_1[0]
            self.dim_2_start = self.dim_2[0]
            
            if all(np.diff(xr_dim_1.values) == np.diff(xr_dim_1.values)[0]):
                self.resolution = abs(xr_dim_1.values[1] - xr_dim_1.values[0])
            else:
                self.resolution = np.mean(np.diff(self.dim_1))
                raise RuntimeWarning("The first dimension is not evenly spaced")
            
            if all(np.diff(xr_dim_2.values) == np.diff(xr_dim_2.values)[0]):
                self.dim_2_resolution = abs(xr_dim_2.values[1] - xr_dim_2.values[0])
            else:
                self.dim_2_resolution = np.mean(np.diff(self.dim_2))
                raise RuntimeWarning("The second dimension is not evenly spaced")
            
            self.mapping = np.arange(len(self.dim_1) * len(self.dim_2)).reshape(len(self.dim_1), len(self.dim_2))
            self.map_shape = self.mapping.shape
        elif dim_1_start is not None and dim_2_start is not None and dim_1_len is not None \
                and dim_2_len is not None and resolution is not None:
            self.create_mapping(dim_1_start, dim_2_start, dim_1_len, dim_2_len, resolution, dim_2_resolution)
        else:
            raise ValueError("Not enough arguments to create the mapping")
    
    def __str__(self):
        ret_str = (
            f"CoordinateMapping:                    \n"
            f"Dims:         {self.dim_names}        \n"
            f"D1start:      {self.dim_1_start}      \n"
            f"D2start:      {self.dim_2_start}      \n"
            f"Shape:        {self.map_shape}        \n"
            f"D1res:        {self.resolution}       \n"
            f"D2res:        {self.dim_2_resolution} \n")
        return ret_str
    
    def create_mapping(self, dim_1_start, dim_2_start, dim_1_len, dim_2_len, resolution, dim_2_resolution=None):
        self.mapping = np.arange(dim_1_len * dim_2_len).reshape(dim_1_len, dim_2_len)
        self.map_shape = self.mapping.shape
        self.dim_1_start = dim_1_start
        self.dim_2_start = dim_2_start
        self.resolution = resolution
        self.dim_2_resolution = dim_2_resolution if dim_2_resolution else resolution
    
    def mapping_area(self):
        x_axis = np.arange(self.dim_1_start,
                           self.dim_1_start + self.map_shape[0] * self.resolution,
                           self.resolution)
        y_axis = np.arange(self.dim_2_start,
                           self.dim_2_start + self.map_shape[1] * self.dim_2_resolution,
                           self.dim_2_resolution)
        x_mesh, y_mesh = np.meshgrid(x_axis, y_axis)
        return np.stack((x_mesh, y_mesh), axis=2)
    
    def mapping_point(self):
        x_axis = np.arange(self.dim_1_start,
                           self.dim_1_start + self.map_shape[0] * self.resolution,
                           self.resolution) + self.resolution / 2
        y_axis = np.arange(self.dim_2_start,
                           self.dim_2_start + self.map_shape[1] * self.dim_2_resolution,
                           self.dim_2_resolution) + self.dim_2_resolution / 2
        x_mesh, y_mesh = np.meshgrid(x_axis, y_axis)
        return np.stack((x_mesh, y_mesh), axis=2)
    
    def get_mapping_index(self, d1_id, d2_id):
        if d1_id < self.mapping.shape[0] and d2_id < self.mapping.shape[1]:
            return self.mapping[d1_id, d2_id]
        else:
            return -1
    
    def sample_index(self, d1_id, d2_id, how='point'):
        if how not in ['point', 'cross', 'square']:
            raise RuntimeError('Only supported point, cross, and square in sampling!')
        
        if how == 'point':
            return [int(self.get_mapping_index(d1_id, d2_id))]
        if how == 'cross':
            return [int(self.get_mapping_index(x, y))
                    for x, y in [(d1_id - 1, d2_id),
                                 (d1_id, d2_id - 1), (d1_id, d2_id), (d1_id, d2_id + 1),
                                 (d1_id + 1, d2_id)]]
        if how == 'square':
            return [int(self.get_mapping_index(x, y))
                    for x, y in itertools.product(*[[d1_id - 1, d1_id, d1_id + 1], [d2_id - 1, d2_id, d2_id + 1]])]
        else:
            # possible to implement other sampling methods, i.e. give a radius, or window size?
            raise RuntimeError('Only supported point, cross, and square in sampling!')
    
    def get_mapping_by_input_coord(self, d1_area, d2_area, how=None, offset=(0, 0)):
        d1_ind = int((d1_area - self.dim_1_start + offset[0]) / self.resolution)
        d2_ind = int((d2_area - self.dim_2_start + offset[1]) / self.dim_2_resolution)
        # get the mapping by coordinate
        if not how:
            return self.get_mapping_index(d1_ind, d2_ind)
        else:
            return self.sample_index(d1_ind, d2_ind, how)
    
    def get_mapping_coord_point(self, d1_point, d2_point, how=None):
        # get the mapping by coordinate
        offset = (- self.resolution / 2, - self.dim_2_resolution / 2)
        return self.get_mapping_by_input_coord(d1_point, d2_point, how=how, offset=offset)
    
    def revert_mapping(self, mapping):
        d1 = mapping // self.map_shape[1]
        d2 = mapping % self.map_shape[1]
        return d1, d2
    
    def revert_mapping_to_input_coords(self, mapping, offset=(0, 0)):
        d1, d2 = self.revert_mapping(mapping)
        return self.dim_1[d1] + offset[0], self.dim_2[d2] + offset[1]
    
    def revert_mapping_to_point_coord(self, mapping):
        return self.revert_mapping_to_input_coords(mapping,
                                                   (self.resolution / 2, self.dim_2_resolution / 2))
    
    def save_mapping_meta(self, directory, name=None):
        if not name:
            time = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
            name = f'mapping_dims_{self.dim_names[0]}_{self.dim_names[1]}_{time}.txt'
        
        with open(os.path.join(directory, name), "w") as file:
            file.write(f"Dims:    {self.dim_names}\n")
            file.write(f"D1start: {self.dim_1_start}\n")
            file.write(f"D2start: {self.dim_2_start}\n")
            file.write(f"Shape:   {self.map_shape}\n")
            file.write(f"res:     {self.resolution}\n")
            file.write(f"D2res:   {self.dim_2_resolution}\n")


if __name__ == '__main__':
    # Define the dimensions
    x_values = np.arange(0, 10, 2)  # Evenly spaced x coordinates
    y_values = np.arange(0, 6, 2)  # Evenly spaced y coordinates
    
    # Create a meshgrid of the coordinates
    x, y = np.meshgrid(x_values, y_values)
    
    # Create some dummy data
    data = np.random.rand(y.shape[0], x.shape[1])
    
    # Create an xarray dataset
    ds = xr.Dataset(
        {
            "data": (["y", "x"], data),  # Data variable
        },
        coords={"x": x_values, "y": y_values},  # Coordinate variables
    )
    
    # Take care of which variable is used first in the mapping, as this might fail silently
    coordinate_map_xy = CoordinateMapping(ds.x, ds.y)
    coordinate_map_yx = CoordinateMapping(ds.y, ds.x)
    
    ds_xy = ds.stack(mapping=('x', 'y'))
    print(ds_xy.mapping.where(ds_xy.x == 0))
    
    ds_xy = ds_xy.assign_coords({"mapping": coordinate_map_xy.mapping.flatten()})
    print(ds_xy.mapping.values == coordinate_map_xy.mapping.flatten())
    