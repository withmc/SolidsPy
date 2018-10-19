# -*- coding: utf-8 -*-
"""
Assembly routines
-----------------

Functions to assemble the system of equations for the Finite Element
Analysis.

"""
from __future__ import absolute_import, division, print_function
import numpy as np
from scipy.sparse import coo_matrix
import solidspy.uelutil as ue
import solidspy.femutil as fem


ELEM_ID = {1: ue.uel4nquad,
           2: ue.uel6ntrian,
           3: ue.uel3ntrian,
           5: ue.uelspring,
           6: ue.ueltruss2D,
           7: ue.uelbeam2DU}


def eqcounter(nodes):
    """Counts active equations and creates BCs array IBC

    Parameters
    ----------
    nodes : ndarray
      Array with nodes coordinates and boundary conditions.

    Returns
    -------
    neq : int
      Number of equations in the system after removing the nodes
      with imposed displacements.
    IBC : ndarray (int)
      Array that maps the nodes with number of equations.

    """
    nnodes = nodes.shape[0]
    IBC = np.zeros([nnodes, 2], dtype=np.integer)
    for i in range(nnodes):
        for k in range(2):
            IBC[i, k] = int(nodes[i, k+3])
    neq = 0
    for i in range(nnodes):
        for j in range(2):
            if IBC[i, j] == 0:
                IBC[i, j] = neq
                neq = neq + 1

    return neq, IBC


def DME(nodes, elements):
    """Counts active equations, creates BCs array IBC[]
    and the assembly operator DME[]

    Parameters
    ----------
    nodes    : ndarray.
      Array with the nodal numbers and coordinates.
    elements : ndarray
      Array with the number for the nodes in each element.

    Returns
    -------
    DME : ndarray (int)
      Assembly operator.
    IBC : ndarray (int)
      Boundary conditions array.
    neq : int
      Number of active equations in the system.

    """
    nels = elements.shape[0]
    IELCON = np.zeros([nels, 9], dtype=np.integer)
    DME = np.zeros([nels, 18], dtype=np.integer)
    neq, IBC = eqcounter(nodes)

    for i in range(nels):
        iet = elements[i, 1]
        ndof, nnodes, ngpts = fem.eletype(iet)
        for j in range(nnodes):
            IELCON[i, j] = elements[i, j+3]
            kk = IELCON[i, j]
            for l in range(2):
                DME[i, 2*j+l] = IBC[kk, l]

    return DME, IBC, neq


def retriever(elements, mats, nodes, i, uel=None):
    """Computes the elemental stiffness matrix of element i

    Parameters
    ----------
    elements : ndarray
      Array with the number for the nodes in each element.
    mats : ndarray.
      Array with the material profiles.
    nodes : ndarray.
      Array with the nodal numbers and coordinates.
    i : int.
      Identifier of the element to be assembled.

    Returns
    -------
    kloc : ndarray (float)
      Array with the local stiffness matrix.
    ndof : int.
      Number of degrees of fredom of the current element.
    iet : integer
      Element identifier.
    """
    IELCON = np.zeros([9], dtype=np.integer)
    elem_type = elements[i, 1]
    ndof, nnodes, ngpts = fem.eletype(elem_type)
    elcoor = np.zeros([nnodes, 2])
    im = np.int(elements[i, 2])
    params = mats[im, :]
    for j in range(nnodes):
        IELCON[j] = elements[i, j+3]
        elcoor[j, 0] = nodes[IELCON[j], 1]
        elcoor[j, 1] = nodes[IELCON[j], 2]
    if uel is None:
        uel = ELEM_ID[elem_type]
        kloc = uel(elcoor, params)
    else:
        kloc, ndof, elem_type = uel(elcoor, params)

    return kloc, ndof, elem_type


def assembler(elements, mats, nodes, neq, DME, sparse=True, uel=None):
    """Assembles the global stiffness matrix

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.
    sparse : boolean (optional)
      Boolean variable to pick sparse assembler. It is True
      by default.
    uel : callable function (optional)
      Python function that returns the local stiffness matrix.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix. It might be
      dense or sparse, depending on the value of _sparse_

    """
    if sparse:
        KG = sparse_assem(elements, mats, nodes, neq, DME, uel=uel)
    else:
        KG = dense_assem(elements, mats, nodes, neq, DME, uel=uel)

    return KG


def dense_assem(elements, mats, nodes, neq, DME, uel=None):
    """
    Assembles the global stiffness matrix _KG_
    using a dense storing scheme

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.
    uel : callable function (optional)
      Python function that returns the local stiffness matrix.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix in a dense numpy
      array.

    """
    KG = np.zeros((neq, neq))
    nels = elements.shape[0]
    for el in range(nels):
        kloc, ndof, iet = retriever(elements, mats, nodes, el, uel=uel)
        dme = DME[el, :ndof]
        for row in range(ndof):
            glob_row = dme[row]
            if glob_row != -1:
                for col in range(ndof):
                    glob_col = dme[col]
                    if glob_col != -1:
                        KG[glob_row, glob_col] = KG[glob_row, glob_col] +\
                                                 kloc[row, col]

    return KG


def sparse_assem(elements, mats, nodes, neq, DME, uel=None):
    """
    Assembles the global stiffness matrix _KG_
    using a sparse storing scheme

    The scheme used to assemble is COOrdinate list (COO), and
    it converted to Compressed Sparse Row (CSR) afterward
    for the solution phase [1]_.

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.
    uel : callable function (optional)
      Python function that returns the local stiffness matrix.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix in a sparse
      Compressed Sparse Row (CSR) format.

    References
    ----------
    .. [1] Sparse matrix. (2017, March 8). In Wikipedia,
        The Free Encyclopedia.
        https://en.wikipedia.org/wiki/Sparse_matrix

    """
    rows = []
    cols = []
    vals = []
    nels = elements.shape[0]
    for el in range(nels):
        kloc, ndof, iet = retriever(elements, mats, nodes, el, uel=uel)
        dme = DME[el, :ndof]

        for row in range(ndof):
            glob_row = dme[row]
            if glob_row != -1:
                for col in range(ndof):
                    glob_col = dme[col]
                    if glob_col != -1:
                        rows.append(glob_row)
                        cols.append(glob_col)
                        vals.append(kloc[row, col])

    return coo_matrix((vals, (rows, cols)), shape=(neq, neq)).tocsr()


def loadasem(loads, IBC, neq):
    """Assembles the global Right Hand Side Vector RHSG

    Parameters
    ----------
    loads : ndarray
      Array with the loads imposed in the system.
    IBC : ndarray (int)
      Array that maps the nodes with number of equations.
    neq : int
      Number of equations in the system after removing the nodes
      with imposed displacements.

    Returns
    -------
    RHSG : ndarray
      Array with the right hand side vector.

    """
    nloads = loads.shape[0]
    RHSG = np.zeros([neq])
    for i in range(nloads):
        il = int(loads[i, 0])
        ilx = IBC[il, 0]
        ily = IBC[il, 1]
        if ilx != -1:
            RHSG[ilx] = loads[i, 1]
        if ily != -1:
            RHSG[ily] = loads[i, 2]

    return RHSG


if __name__ == "__main__":
    import doctest
    doctest.testmod()
