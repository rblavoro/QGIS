# -*- coding: utf-8 -*-

"""
***************************************************************************
    PointsInPolygon.py
    ---------------------
    Date                 : August 2012
    Copyright            : (C) 2012 by Victor Olaya
    Email                : volayaf at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from builtins import str

__author__ = 'Victor Olaya'
__date__ = 'August 2012'
__copyright__ = '(C) 2012, Victor Olaya'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsApplication,
                       QgsField,
                       QgsFeatureRequest,
                       QgsFeatureSink,
                       QgsFeature,
                       QgsGeometry,
                       QgsProcessingUtils)
from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm
from processing.core.parameters import ParameterVector
from processing.core.parameters import ParameterString
from processing.core.parameters import ParameterTableField
from processing.core.outputs import OutputVector
from processing.tools import dataobjects, vector


class PointsInPolygonWeighted(QgisAlgorithm):

    POLYGONS = 'POLYGONS'
    POINTS = 'POINTS'
    OUTPUT = 'OUTPUT'
    FIELD = 'FIELD'
    WEIGHT = 'WEIGHT'

    def group(self):
        return self.tr('Vector analysis tools')

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.addParameter(ParameterVector(self.POLYGONS,
                                          self.tr('Polygons'), [dataobjects.TYPE_VECTOR_POLYGON]))
        self.addParameter(ParameterVector(self.POINTS,
                                          self.tr('Points'), [dataobjects.TYPE_VECTOR_POINT]))
        self.addParameter(ParameterTableField(self.WEIGHT,
                                              self.tr('Weight field'), self.POINTS))
        self.addParameter(ParameterString(self.FIELD,
                                          self.tr('Count field name'), 'NUMPOINTS'))

        self.addOutput(OutputVector(self.OUTPUT, self.tr('Weighted count'), datatype=[dataobjects.TYPE_VECTOR_POLYGON]))

    def name(self):
        return 'countpointsinpolygonweighted'

    def displayName(self):
        return self.tr('Count points in polygon(weighted)')

    def processAlgorithm(self, parameters, context, feedback):
        polyLayer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.POLYGONS), context)
        pointLayer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.POINTS), context)
        fieldName = self.getParameterValue(self.FIELD)
        fieldIdx = pointLayer.fields().lookupField(self.getParameterValue(self.WEIGHT))

        fields = polyLayer.fields()
        fields.append(QgsField(fieldName, QVariant.Int))

        (idxCount, fieldList) = vector.findOrCreateField(polyLayer,
                                                         polyLayer.fields(), fieldName)

        writer = self.getOutputFromName(self.OUTPUT).getVectorWriter(fields, polyLayer.wkbType(),
                                                                     polyLayer.crs(), context)

        spatialIndex = QgsProcessingUtils.createSpatialIndex(pointLayer, context)

        ftPoint = QgsFeature()
        outFeat = QgsFeature()
        geom = QgsGeometry()

        features = QgsProcessingUtils.getFeatures(polyLayer, context)
        total = 100.0 / polyLayer.featureCount() if polyLayer.featureCount() else 0
        for current, ftPoly in enumerate(features):
            geom = ftPoly.geometry()
            engine = QgsGeometry.createGeometryEngine(geom.geometry())
            engine.prepareGeometry()

            attrs = ftPoly.attributes()

            count = 0
            points = spatialIndex.intersects(geom.boundingBox())
            if len(points) > 0:
                feedback.setProgressText(str(len(points)))
                request = QgsFeatureRequest().setFilterFids(points).setSubsetOfAttributes([fieldIdx])
                fit = pointLayer.getFeatures(request)
                ftPoint = QgsFeature()
                while fit.nextFeature(ftPoint):
                    tmpGeom = QgsGeometry(ftPoint.geometry())
                    if engine.contains(tmpGeom.geometry()):
                        weight = str(ftPoint.attributes()[fieldIdx])
                        try:
                            count += float(weight)
                        except:
                            # Ignore fields with non-numeric values
                            pass

            outFeat.setGeometry(geom)
            if idxCount == len(attrs):
                attrs.append(count)
            else:
                attrs[idxCount] = count
            outFeat.setAttributes(attrs)
            writer.addFeature(outFeat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(current * total))

        del writer
