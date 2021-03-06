# -*- coding: utf-8 -*-

"""
***************************************************************************
    PointOnSurface.py
    --------------
    Date                 : July 2016
    Copyright            : (C) 2016 by Nyall Dawson
    Email                : nyall dot dawson at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Nyall Dawson'
__date__ = 'July 2016'
__copyright__ = '(C) 2016, Nyall Dawson'

# This will get replaced with a git SHA1 when you do a git archive323

__revision__ = '$Format:%H$'

import os

from qgis.core import QgsWkbTypes, QgsFeatureSink, QgsProcessingUtils

from qgis.PyQt.QtGui import QIcon

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm
from processing.core.GeoAlgorithmExecutionException import GeoAlgorithmExecutionException
from processing.core.parameters import ParameterVector
from processing.core.outputs import OutputVector
from processing.tools import dataobjects

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class PointOnSurface(QgisAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'images', 'ftools', 'centroids.png'))

    def group(self):
        return self.tr('Vector geometry tools')

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.addParameter(ParameterVector(self.INPUT_LAYER,
                                          self.tr('Input layer')))
        self.addOutput(OutputVector(self.OUTPUT_LAYER, self.tr('Point'), datatype=[dataobjects.TYPE_VECTOR_POINT]))

    def name(self):
        return 'pointonsurface'

    def displayName(self):
        return self.tr('Point on surface')

    def processAlgorithm(self, parameters, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.INPUT_LAYER), context)

        writer = self.getOutputFromName(
            self.OUTPUT_LAYER).getVectorWriter(layer.fields(), QgsWkbTypes.Point, layer.crs(), context)

        features = QgsProcessingUtils.getFeatures(layer, context)
        total = 100.0 / layer.featureCount() if layer.featureCount() else 0

        for current, input_feature in enumerate(features):
            output_feature = input_feature
            input_geometry = input_feature.geometry()
            if input_geometry:
                output_geometry = input_geometry.pointOnSurface()
                if not output_geometry:
                    raise GeoAlgorithmExecutionException(
                        self.tr('Error calculating point on surface'))

                output_feature.setGeometry(output_geometry)

            writer.addFeature(output_feature, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(current * total))

        del writer
