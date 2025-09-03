import streamlit as st
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import KDTree
import tempfile
import os

st.set_page_config(page_title="Duplicate House Number Finder", layout="wide")

st.title("🏠 Duplicate House Number Finder")
st.markdown("Upload a geodatabase (GDB) or GeoPackage and detect duplicate house numbers within a distance threshold.")

# Upload file
uploaded_file = st.file_uploader("Upload your file (.gdb zipped, .gpkg, or .shp as zip)", type=["zip", "gpkg", "gdb"])

if uploaded_file is not None:
    # Save uploaded file to a temporary location
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.read())

        # If zip (shapefile or gdb), extract
        if uploaded_file.name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            # Look for .shp or .gdb inside
            shp_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".shp")]
            gdb_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".gdb")]

            if shp_files:
                gdf = gpd.read_file(shp_files[0])
            elif gdb_files:
                layers = f"{gdb_files[0]}"
                st.info(f"Found GDB: {layers}. Please enter layer name below.")
                layer_name = st.text_input("Enter layer name to read from GDB")
                if layer_name:
                    gdf = gpd.read_file(gdb_files[0], layer=layer_name)
                else:
                    st.stop()
            else:
                st.error("No shapefile or GDB found inside zip.")
                st.stop()

        elif uploaded_file.name.endswith(".gpkg"):
            layers = gpd.io.file.fiona.listlayers(file_path)
            st.info(f"Available layers: {layers}")
            layer_name = st.selectbox("Choose a layer", layers)
            gdf = gpd.read_file(file_path, layer=layer_name)

        else:
            st.error("Unsupported format. Please upload zip (shp/gdb) or gpkg.")
            st.stop()

        # Show columns
        st.write("### Available columns:", list(gdf.columns))

        # Choose the house number field
        house_num_field = st.selectbox("Select the House Number field", gdf.columns)

        # Distance threshold
        distance_threshold = st.number_input("Distance threshold (meters)", min_value=1, value=25)

        if st.button("🔍 Find Duplicates"):
            # Ensure CRS is in WGS84 → UTM
            gdf = gdf.to_crs(epsg=4326)
            gdf = gdf.to_crs(epsg=32640)  # You might want to auto-detect UTM based on location

            coords = list(zip(gdf.geometry.x, gdf.geometry.y))
            house_numbers = gdf[house_num_field].astype(str).tolist()

            kdtree = KDTree(coords)
            duplicate_indices = set()

            for i, (point, house_number) in enumerate(zip(coords, house_numbers)):
                indices = kdtree.query_ball_point(point, distance_threshold)
                for j in indices:
                    if j != i and house_numbers[j] == house_number:
                        duplicate_indices.add(i)
                        duplicate_indices.add(j)

            duplicate_points = gdf.iloc[list(duplicate_indices)]

            st.success(f"✅ Found {len(duplicate_points)} duplicate points")

            st.write("### Duplicate points preview")
            st.dataframe(duplicate_points[[house_num_field, "geometry"]].head())

            # Export option
            output_path = os.path.join(tmpdir, "duplicates.gpkg")
            duplicate_points.to_file(output_path, driver="GPKG")

            with open(output_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download Duplicate Points (GeoPackage)",
                    data=f,
                    file_name="duplicates.gpkg",
                    mime="application/octet-stream"
                )
