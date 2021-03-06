r"""
Fixed-Radius Nearest Neighbors Search
=====================================
Cell lists algorithm partitions space into grid and sorts points into a cell in
discrete grid, allowing *fast nearest neighbor searches* for *fixed radius*
because it is only necessary to search current and neighboring cells for points
instead of the whole domain.


Inserting the Points into Cells
-------------------------------
Point in :math:`n \in \mathbb{N}` dimension is denoted

.. math::
   \mathbf{p}_i \in \mathbb{R}^n

An sequence of points of size :math:`N`, for which index set is
:math:`J = \{0,\ldots ,N-1\}`, is denoted

.. math::
   (\mathbf{p}_i)_{i \in J}

A cell of size :math:`c > 0` for point :math:`i` is calculated

.. math::
   \mathbf{c}_i = \left\lfloor \frac{\mathbf{p}_i}{c} \right\rfloor

Algorithm

1. Compute the shape of the grid
2. Add ghost cells into the shape
3. Count the number of points that belong to each cell
4. Cumulative sum of the counts
5. Sort the indices of the points in order which they appear in the cells and
   store them in an array.


Finding Nearest Neighbors
-------------------------


Computational Complexity
------------------------
Brute force

.. math::
   \mathcal{O}(N^2)

Cell lists

.. math::
   \mathcal{O}(N k)


Memory Usage
------------


References
----------
.. [FRNNS] Fixed-radius near neighbors. (2017). En.wikipedia.org. Retrieved 10 July 2017, from https://en.wikipedia.org/wiki/Fixed-radius_near_neighbors
.. [celllists] Cell lists. (2017). En.wikipedia.org. Retrieved 10 July 2017, from https://en.wikipedia.org/wiki/Cell_lists
.. [Bentley75] Bentley, J. L. (1975). A Survey of techniques for fixed radius near neighbor searching, 37.
.. [Lecture2] Lecture 2 : Fixed-Radius Near Neighbors and Geometric Basics. (1977), 5–16.
.. [Hoetzlein14] Hoetzlein, R. (2014). Fast Fixed-Radius Nearest Neighbors: Interactive Million-Particle Fluids. GPU Technology Conference.

----
"""
import numba
import numpy as np
from numba import f8, i8
import itertools


@numba.jit([(f8[:, :], f8)], nopython=True, nogil=True, cache=True)
def add_to_cells(points, cell_size):
    r"""Sorts the indices of the points into the grid by the given cell size.

    Parameters
    ----------
    points : array of floats
        A sequence points :math:`\mathbf{p}_i` that we want to search for
        nearest neighbors.
    cell_size : float
        Positive real number :math:`c > 0` denoting the cell size of the grid.

    Returns
    -------
    (numpy.ndarray, numpy.ndarray, numpy.ndarray, numpy.ndarray)
        Tuple of arrays where the elements are

        - **points_indices** -- Array of integers for querying the indices of
          nearest neighbors.
        - **cells_count** -- Array of integers denoting the number of points
          inside each cell.
        - **cells_offset** -- Array of integers denoting the offset index for
          each cell in **points_indices** array.
        - **grid_shape** -- Array of integers denoting the shape of the output grid.

    """
    assert cell_size > 0 and points.ndim == 2

    # Size and dimensions of the points.
    size, dimensions = points.shape

    # Here we compute the ranges (min, max) for indices.
    x_min = (points[0, :] / cell_size).astype(np.int64)
    x_max = (points[0, :] / cell_size).astype(np.int64)

    for i in range(1, size):
        for j in range(dimensions):
            x = np.int64(points[i, j] / cell_size)
            if x < x_min[j]:
                x_min[j] = x
            if x > x_max[j]:
                x_max[j] = x

    # Shape of the grid of bins.
    # +1 is for converting from indexing to size.
    # +2 is the padding from ghost cells which are extra cells for iterating
    # over the cells without having to do complicated bounds checks.
    grid_shape = (x_max - x_min) + 1 + 2
    grid_size = np.prod(grid_shape)

    # Here we compute in which cell every point belongs to. Normalized by
    # subtracting minimum index for each dimension.
    cells = np.empty(size, dtype=np.int64)
    for i in range(size):
        l = np.int64(points[i, 0] / cell_size) - x_min[0] + 1
        for j in range(1, dimensions):
            l *= grid_shape[j]
            l += np.int64(points[i, j] / cell_size) - x_min[j] + 1
        cells[i] = l

    # Count the number of points that go into each cell.
    cells_count = np.zeros(shape=grid_size, dtype=np.int64)
    for l in cells:
        cells_count[l] += 1

    # Allocate array for saving indices of the points into the cell they belong
    # and the amount of offset their index has in the array.
    points_indices = np.empty(size, dtype=np.int64)
    cells_offset = np.cumsum(cells_count)
    for i, l in enumerate(cells):
        # Assign the cell index of the current point into the place in the array
        # denoted by the offset. Decrement the offset.
        offset = cells_offset[l]
        points_indices[offset - 1] = i
        cells_offset[l] -= 1

    return points_indices, cells_count, cells_offset, grid_shape


@numba.jit([(i8[:, :], i8[:])], nopython=True, nogil=True, cache=True)
def _neighboring_cells(prod, grid_shape):
    size = len(prod)
    cells = np.empty(size, dtype=np.int64)

    for k in range(size):
        l = prod[k, 0]
        for i, n in zip(prod[k, 1:], grid_shape[1:]):
            l = l * n + i
        cells[k] = l

    return cells


def neighboring_cells(grid_shape, distance=1):
    r"""Neighboring cells.

    Parameters
    ----------
    grid_shape
    distance : int
        The maximum distance :math:`d \in \mathbb{N}` of nearest neighboring
        cells.

    Returns
    -------
    numpy.ndarray
        Array of differences of the indices of neighboring cells.

    """
    assert isinstance(distance, int) and distance >= 1
    base = tuple(range(-distance, distance + 1))
    prod = list(itertools.product(*len(grid_shape) * (base,)))
    prod_ = np.array(prod[len(prod) // 2 + 1:])
    return _neighboring_cells(prod_, grid_shape)


@numba.jit([i8[:](i8, i8[:], i8[:], i8[:])],
           nopython=True, nogil=True, cache=True)
def find_points_in_cell(cell_index, points_indices, cells_count, cells_offset):
    r"""Return indices of points inside cell of cell_index.

    Parameters
    ----------
    cell_index
    points_indices
    cells_count
    cells_offset

    Returns
    -------
    numpy.ndarray

    """
    start = cells_offset[cell_index]
    end = start + cells_count[cell_index]
    return points_indices[start:end]


@numba.jit([(i8[:], i8[:], i8[:], i8[:], i8[:])], nopython=True, nogil=True)
def iter_nearest_neighbors(cell_indices, neigh_cells, points_indices, cells_count,
                           cells_offset):
    r"""Iterate over cell lists

    Parameters
    ----------
    cell_indices
        Indices of the cells to which iterate over.
        `np.arange(len(cells_count))`
    neigh_cells
    points_indices
    cells_count
    cells_offset

    Yields
    ------
    (int, int)
        Tuple of indices of a pair of nearest neighbors.

    """
    for cur_cell in cell_indices:
        if cells_count[cur_cell] == 0:
            continue

        points_cur = find_points_in_cell(
            cur_cell, points_indices, cells_count, cells_offset)
        for k, i in enumerate(points_cur[:-1]):
            for j in points_cur[k + 1:]:
                yield i, j

        for neigh_cell in neigh_cells:
            points_neigh = find_points_in_cell(
                cur_cell + neigh_cell, points_indices, cells_count,
                cells_offset)
            for i in points_cur:
                for j in points_neigh:
                    yield i, j


@numba.jit([(i8, i8[:], i8[:])], nopython=True, nogil=True, cache=True)
def partition_cells(n, cells_count, neigh_cells):
    r"""Split cells equally by the amount of interactions between agents in
    an cell and neighboring cells.

    Parameters
    ----------
    n : int
        Number of parts to split cells.
    neigh_cells
    cells_count

    Returns
    -------
    numpy.array
        Array of the indices to slice the array for the splits.

    """
    assert n > 0

    # Compute cumulative sum of number of interactions per cell.
    interactions_total = 0
    interactions_cumsum = np.empty_like(cells_count)

    for i, count in enumerate(cells_count):
        if count == 0:
            continue
        interactions_total += (count - 1) ** 2
        for j in neigh_cells:
            interactions_total += count * cells_count[i + j]
        interactions_cumsum[i] = interactions_total

    # Split the cells into parts that have equal amount of interactions.
    size = np.int64(np.ceil(interactions_total / n))
    splits = np.empty(n + 1, dtype=np.int64)
    splits[0] = 0
    splits[-1] = len(cells_count)

    part_index = 1
    i = 0
    while part_index < n:
        if interactions_cumsum[i] >= part_index * size:
            splits[part_index] = i
            part_index += 1
        i += 1

    return splits
