import streamlit as st
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import KDTree
import tempfile
import os
import zipfile

st.set_page_config(page_title="Duplicate House Number Finder", layout="wide")

st.title("🏠 Duplicate House Number Finder")
st.markdown("Upload a geodatabase (GDB), GeoPackage (GPKG), or Shapefile (ZIP) and detect duplicate house numbers within a distance threshold, optionally combined with other attributes.")

# ---------------- File Upload ----------------
uploaded_file = st.file_uploader(
    "Upload your file (.gdb zipped, .gpkg, or .shp as zip)", 
    type=["zip", "gpkg", "gdb"]
)

if uploaded_file is not None:
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.read())

        # Handle zipped shapefile or GDB
        if uploaded_file.name.endswith(".zip"):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            shp_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".shp")]
            gdb_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".gdb")]

            if shp_files:
                gdf = gpd.read_file(shp_files[0])
            elif gdb_files:
                st.info("Found GDB. Please enter the layer name.")
                layer_name = st.text_input("Enter layer name from GDB")
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
            st.error("Unsupported format. Please upload .zip (shp/gdb) or .gpkg.")
            st.stop()

        # ---------------- User Input ----------------
        st.write("### Available columns:", list(gdf.columns))

        # House number field
        house_num_field = st.selectbox("Select the House Number field", gdf.columns)

        # Extra attributes for composite duplicate check
        extra_fields = st.multiselect(
            "Select additional attributes to combine with House Number (optional)",
            [col for col in gdf.columns if col != house_num_field]
        )

        # Distance threshold
        distance_threshold = st.number_input(
            "Distance threshold (meters)", 
            min_value=1, 
            value=25
        )

        # ---------------- Duplicate Detection ----------------
        if st.button("🔍 Find Duplicates"):
            # Ensure CRS: WGS84 → UTM (adjust for your region if needed)
            gdf = gdf.to_crs(epsg=4326).to_crs(epsg=32640)

            coords = list(zip(gdf.geometry.x, gdf.geometry.y))

            # Build composite key
            def make_key(row):
                parts = [str(row[house_num_field])]
                for f in extra_fields:
                    parts.append(str(row[f]))
                return "|".join(parts)

            composite_keys = gdf.apply(make_key, axis=1).tolist()

            kdtree = KDTree(coords)
            duplicate_indices = set()

            for i, (point, comp_key) in enumerate(zip(coords, composite_keys)):
                indices = kdtree.query_ball_point(point, distance_threshold)
                for j in indices:
                    if j != i and composite_keys[j] == comp_key:
                        duplicate_indices.add(i)
                        duplicate_indices.add(j)

            duplicate_points = gdf.iloc[list(duplicate_indices)]

            st.success(f"✅ Found {len(duplicate_points)} duplicate points")

            # Preview
            st.write("### Duplicate points preview")
            preview_cols = [house_num_field] + extra_fields + ["geometry"]
            st.dataframe(duplicate_points[preview_cols].head())

            # ---------------- Export ----------------
            output_path = os.path.join(tmpdir, "duplicates.gpkg")
            duplicate_points.to_file(output_path, driver="GPKG")

            with open(output_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download Duplicate Points (GeoPackage)",
                    data=f,
                    file_name="duplicates.gpkg",
                    mime="application/octet-stream"
                )
