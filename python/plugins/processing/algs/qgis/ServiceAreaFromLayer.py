# -*- coding: utf-8 -*-

"""
***************************************************************************
    ServiceAreaFromLayer.py
    ---------------------
    Date                 : December 2016
    Copyright            : (C) 2016 by Alexander Bruy
    Email                : alexander dot bruy at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Alexander Bruy'
__date__ = 'December 2016'
__copyright__ = '(C) 2016, Alexander Bruy'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsWkbTypes,
                       QgsUnitTypes,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsGeometry,
                       QgsField,
                       QgsFields,
                       QgsFeatureRequest,
                       QgsProcessingUtils,
                       QgsProcessingParameterDefinition)
from qgis.analysis import (QgsVectorLayerDirector,
                           QgsNetworkDistanceStrategy,
                           QgsNetworkSpeedStrategy,
                           QgsGraphBuilder,
                           QgsGraphAnalyzer
                           )
from qgis.utils import iface

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm
from processing.core.parameters import (ParameterVector,
                                        ParameterNumber,
                                        ParameterString,
                                        ParameterTableField,
                                        ParameterSelection
                                        )
from processing.core.outputs import OutputVector
from processing.tools import dataobjects

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class ServiceAreaFromLayer(QgisAlgorithm):

    INPUT_VECTOR = 'INPUT_VECTOR'
    START_POINTS = 'START_POINTS'
    STRATEGY = 'STRATEGY'
    TRAVEL_COST = 'TRAVEL_COST'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    OUTPUT_POINTS = 'OUTPUT_POINTS'
    OUTPUT_POLYGON = 'OUTPUT_POLYGON'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'images', 'networkanalysis.svg'))

    def group(self):
        return self.tr('Network analysis')

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionForward)])

        self.STRATEGIES = [self.tr('Shortest'),
                           self.tr('Fastest')
                           ]

        self.addParameter(ParameterVector(self.INPUT_VECTOR,
                                          self.tr('Vector layer representing network'),
                                          [dataobjects.TYPE_VECTOR_LINE]))
        self.addParameter(ParameterVector(self.START_POINTS,
                                          self.tr('Vector layer with start points'),
                                          [dataobjects.TYPE_VECTOR_POINT]))
        self.addParameter(ParameterSelection(self.STRATEGY,
                                             self.tr('Path type to calculate'),
                                             self.STRATEGIES,
                                             default=0))
        self.addParameter(ParameterNumber(self.TRAVEL_COST,
                                          self.tr('Travel cost (distance for "Shortest", time for "Fastest")'),
                                          0.0, 99999999.999999, 0.0))

        params = []
        params.append(ParameterTableField(self.DIRECTION_FIELD,
                                          self.tr('Direction field'),
                                          self.INPUT_VECTOR,
                                          optional=True))
        params.append(ParameterString(self.VALUE_FORWARD,
                                      self.tr('Value for forward direction'),
                                      '',
                                      optional=True))
        params.append(ParameterString(self.VALUE_BACKWARD,
                                      self.tr('Value for backward direction'),
                                      '',
                                      optional=True))
        params.append(ParameterString(self.VALUE_BOTH,
                                      self.tr('Value for both directions'),
                                      '',
                                      optional=True))
        params.append(ParameterSelection(self.DEFAULT_DIRECTION,
                                         self.tr('Default direction'),
                                         list(self.DIRECTIONS.keys()),
                                         default=2))
        params.append(ParameterTableField(self.SPEED_FIELD,
                                          self.tr('Speed field'),
                                          self.INPUT_VECTOR,
                                          optional=True))
        params.append(ParameterNumber(self.DEFAULT_SPEED,
                                      self.tr('Default speed (km/h)'),
                                      0.0, 99999999.999999, 5.0))
        params.append(ParameterNumber(self.TOLERANCE,
                                      self.tr('Topology tolerance'),
                                      0.0, 99999999.999999, 0.0))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addOutput(OutputVector(self.OUTPUT_POINTS,
                                    self.tr('Service area (boundary nodes)'),
                                    datatype=[dataobjects.TYPE_VECTOR_POINT]))
        self.addOutput(OutputVector(self.OUTPUT_POLYGON,
                                    self.tr('Service area (convex hull)'),
                                    datatype=[dataobjects.TYPE_VECTOR_POLYGON]))

    def name(self):
        return 'serviceareafromlayer'

    def displayName(self):
        return self.tr('Service area (from layer)')

    def processAlgorithm(self, parameters, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.INPUT_VECTOR), context)
        startPoints = QgsProcessingUtils.mapLayerFromString(self.getParameterValue(self.START_POINTS), context)
        strategy = self.getParameterValue(self.STRATEGY)
        travelCost = self.getParameterValue(self.TRAVEL_COST)

        directionFieldName = self.getParameterValue(self.DIRECTION_FIELD)
        forwardValue = self.getParameterValue(self.VALUE_FORWARD)
        backwardValue = self.getParameterValue(self.VALUE_BACKWARD)
        bothValue = self.getParameterValue(self.VALUE_BOTH)
        defaultDirection = self.getParameterValue(self.DEFAULT_DIRECTION)
        bothValue = self.getParameterValue(self.VALUE_BOTH)
        defaultDirection = self.getParameterValue(self.DEFAULT_DIRECTION)
        speedFieldName = self.getParameterValue(self.SPEED_FIELD)
        defaultSpeed = self.getParameterValue(self.DEFAULT_SPEED)
        tolerance = self.getParameterValue(self.TOLERANCE)

        fields = QgsFields()
        fields.append(QgsField('type', QVariant.String, '', 254, 0))
        fields.append(QgsField('start', QVariant.String, '', 254, 0))

        feat = QgsFeature()
        feat.setFields(fields)

        writerPoints = self.getOutputFromName(
            self.OUTPUT_POINTS).getVectorWriter(fields, QgsWkbTypes.MultiPoint, layer.crs(), context)

        writerPolygons = self.getOutputFromName(
            self.OUTPUT_POLYGON).getVectorWriter(fields, QgsWkbTypes.Polygon, layer.crs(), context)

        directionField = -1
        if directionFieldName is not None:
            directionField = layer.fields().lookupField(directionFieldName)
        speedField = -1
        if speedFieldName is not None:
            speedField = layer.fields().lookupField(speedFieldName)

        director = QgsVectorLayerDirector(layer,
                                          directionField,
                                          forwardValue,
                                          backwardValue,
                                          bothValue,
                                          defaultDirection)

        distUnit = iface.mapCanvas().mapSettings().destinationCrs().mapUnits()
        multiplier = QgsUnitTypes.fromUnitToUnitFactor(distUnit, QgsUnitTypes.DistanceMeters)
        if strategy == 0:
            strategy = QgsNetworkDistanceStrategy()
        else:
            strategy = QgsNetworkSpeedStrategy(speedField,
                                               defaultSpeed,
                                               multiplier * 1000.0 / 3600.0)

        director.addStrategy(strategy)
        builder = QgsGraphBuilder(iface.mapCanvas().mapSettings().destinationCrs(),
                                  True,
                                  tolerance)

        feedback.pushInfo(self.tr('Loading start points...'))
        request = QgsFeatureRequest()
        request.setFlags(request.flags() ^ QgsFeatureRequest.SubsetOfAttributes)
        features = QgsProcessingUtils.getFeatures(startPoints, context, request)
        points = []
        for f in features:
            points.append(f.geometry().asPoint())

        feedback.pushInfo(self.tr('Building graph...'))
        snappedPoints = director.makeGraph(builder, points)

        feedback.pushInfo(self.tr('Calculating service areas...'))
        graph = builder.graph()

        vertices = []
        upperBoundary = []
        lowerBoundary = []
        total = 100.0 / len(snappedPoints) if snappedPoints else 1
        for i, p in enumerate(snappedPoints):
            idxStart = graph.findVertex(snappedPoints[i])
            origPoint = points[i].toString()

            tree, cost = QgsGraphAnalyzer.dijkstra(graph, idxStart, 0)
            for j, v in enumerate(cost):
                if v > travelCost and tree[j] != -1:
                    vertexId = graph.edge(tree[j]).outVertex()
                    if cost[vertexId] <= travelCost:
                        vertices.append(j)

            for j in vertices:
                upperBoundary.append(graph.vertex(graph.edge(tree[j]).inVertex()).point())
                lowerBoundary.append(graph.vertex(graph.edge(tree[j]).outVertex()).point())

            geomUpper = QgsGeometry.fromMultiPoint(upperBoundary)
            geomLower = QgsGeometry.fromMultiPoint(lowerBoundary)

            feat.setGeometry(geomUpper)
            feat['type'] = 'upper'
            feat['start'] = origPoint
            writerPoints.addFeature(feat, QgsFeatureSink.FastInsert)

            feat.setGeometry(geomLower)
            feat['type'] = 'lower'
            feat['start'] = origPoint
            writerPoints.addFeature(feat, QgsFeatureSink.FastInsert)

            upperBoundary.append(origPoint)
            lowerBoundary.append(origPoint)
            geomUpper = QgsGeometry.fromMultiPoint(upperBoundary)
            geomLower = QgsGeometry.fromMultiPoint(lowerBoundary)

            geom = geomUpper.convexHull()
            feat.setGeometry(geom)
            feat['type'] = 'upper'
            feat['start'] = origPoint
            writerPolygons.addFeature(feat, QgsFeatureSink.FastInsert)

            geom = geomLower.convexHull()
            feat.setGeometry(geom)
            feat['type'] = 'lower'
            feat['start'] = origPoint
            writerPolygons.addFeature(feat, QgsFeatureSink.FastInsert)

            vertices[:] = []
            upperBoundary[:] = []
            lowerBoundary[:] = []

            feedback.setProgress(int(i * total))

        del writerPoints
        del writerPolygons
