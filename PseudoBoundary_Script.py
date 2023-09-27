import uuid
import arcpy
import geopandas as gpd

input_layer = arcpy.GetParameterAsText(0)
output_layer = arcpy.GetParameterAsText(1)
threshold = arcpy.GetParameterAsText(2)
gap = arcpy.GetParameterAsText(3)
bound_guid = arcpy.GetParameterAsText(4)
id_prefix = arcpy.GetParameterAsText(5)


def convexhull(selected_lines, polygons, crs, count):
    # Create a new feature class with the selected lines
    selected_lines_fc = 'in_memory/selected_lines'
    arcpy.Delete_management(selected_lines_fc)
    arcpy.CreateFeatureclass_management("in_memory", "selected_lines", "POLYLINE", spatial_reference=crs)
    with arcpy.da.InsertCursor(selected_lines_fc, ['SHAPE@']) as ins_cursor:
        for line in selected_lines:
            ins_cursor.insertRow([line])

    # Create a convex hull around the line features
    convex_hull_fc = 'in_memory/convex_hull' + str(count)
    arcpy.Delete_management(convex_hull_fc)
    arcpy.MinimumBoundingGeometry_management(selected_lines_fc, convex_hull_fc,
                                             'CONVEX_HULL', 'ALL', '', 'NO_MBG_FIELDS')

    # Append the convex hull to the list of polygons
    polygons.append(convex_hull_fc)


def PseudoBoundary(input_layer, output_layer, threshold, gap, bound_guid, id_prefix):
    # set environment
    split_path = input_layer.split("\\")
    gdb_path = "\\".join(split_path[:-1])
    layer = split_path[-1]

    arcpy.env.workspace = gdb_path

    # Get the spatial reference
    desc = arcpy.Describe(input_layer)
    crs = desc.spatialReference

    # Calculate the length in miles and add it as a new field
    arcpy.AddField_management(input_layer, 'len_miles', 'DOUBLE')
    arcpy.CalculateGeometryAttributes_management(input_layer, [['len_miles', 'LENGTH_GEODESIC']],
                                                 'MILES_US')

    # Sort the features by a field (you can change this to match your requirements)
    # arcpy.Sort_management(input_layer, 'sorted_layer', [['SHAPE', 'ASCENDING']])

    # Read the geodatabase layer using GeoPandas
    input_layer1 = gpd.read_file(gdb_path, driver="OpenFileGDB", layer=layer)

    # Sort the GeoDataFrame by coordinates
    sorted_rows = input_layer1.sort_values(by='geometry')

    # save into featureclass
    sorted_layer = 'sorted'
    sorted_rows.to_file(gdb_path, layer=sorted_layer, driver="OpenFileGDB")

    # initialize values
    polygons = []
    selected_lines = []
    total = 0
    count = 0
    distance = 0

    # convert gap distance to feet
    gap_f = float(gap) * 5820

    # Initialize variables to store the previous point
    prev_x, prev_y = None, None

    # Count the number of features in the feature class
    feature_count = arcpy.management.GetCount(sorted_layer)

    arcpy.env.workspace = gdb_path

    # Iterate through the selected lines
    with arcpy.da.SearchCursor(sorted_layer, ['SHAPE@', 'len_miles']) as cursor:
        for row in cursor:
            count = count + 1
            len_miles = row[1]
            total += len_miles
            print(count)

            # take the x,y coordinates first from a line segment point
            pnt = row[0][0][0]
            x, y = pnt.X, pnt.Y

            # Check if this is not the first point
            if prev_x is not None and prev_y is not None:
                # Calculate distance between the current and previous point
                distance = ((x - prev_x) ** 2 + (y - prev_y) ** 2) ** 0.5
                # print(count, "Distance from previous point:", distance)

            # Update previous point
            prev_x, prev_y = x, y

            # condition for checking threshold and gap distance
            if total >= float(threshold) or distance > gap_f:
                # create convex hull
                convexhull(polygons=polygons, selected_lines=selected_lines, crs=crs, count=count)

                # initialize again
                selected_lines = []
                total = 0

                # add selected one to new list
                selected_lines.append(row[0])

            elif count == int(feature_count.getOutput(0)):
                selected_lines.append(row[0])

                # create convex hull
                convexhull(polygons=polygons, selected_lines=selected_lines, crs=crs, count=count)

            else:
                # add to line list
                selected_lines.append(row[0])

    # Merge all polygons into a single feature class
    merged_polygon = "merged"
    arcpy.Merge_management(polygons, merged_polygon)

    # Remove overlaps between polygons
    arcpy.analysis.RemoveOverlapMultiple(merged_polygon, output_layer, "CENTER_LINE", "ALL")

    # Remove temporary files
    arcpy.Delete_management(merged_polygon)
    arcpy.Delete_management(sorted_layer)

    # Specify fields
    arcpy.DeleteField_management(output_layer, "Id")

    arcpy.management.AddField(output_layer, "Id", field_type="TEXT", field_length=255)
    arcpy.management.AddField(output_layer, "ExternalId", field_type="TEXT", field_length=38)
    arcpy.management.AddField(output_layer, "CustomerBo", field_type="TEXT", field_length=255)
    arcpy.management.AddField(output_layer, "Descriptio", field_type="TEXT", field_length=255)

    # Constant values to update
    constant_value = id_prefix
    boundary_type = bound_guid

    # Update table data structure
    count = 1
    with arcpy.da.UpdateCursor(output_layer, ['Id', 'ExternalId', 'CustomerBo', 'Descriptio']) as cursor:
        for row in cursor:
            row[1] = constant_value + '-' + str(count)
            row[0] = "{" + str(uuid.uuid4()) + "}"
            row[2] = boundary_type
            row[3] = row[1]

            cursor.updateRow(row)
            count = count + 1

    # delete unwanted columns
    arcpy.DeleteField_management(output_layer, "ORIG_FID")

    print('completed')


# Example usage
PseudoBoundary(input_layer=input_layer, output_layer=output_layer, threshold=threshold, gap=gap, bound_guid=bound_guid,
               id_prefix=id_prefix)
