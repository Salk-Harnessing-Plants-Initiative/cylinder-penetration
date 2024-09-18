import numpy as np
import pandas as pd
import argparse
import os
import cv2
import seaborn as sns
from scipy import stats
import matplotlib.pyplot as plt


def get_layer_boundary(image):
    img_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    img_crop = img_gray[:, -200:-100]  # remove the left and right 200 pixels
    # img_crop_r = img_gray[:, -200:-100]
    # img_crop = np.concatenate((img_crop_l, img_crop_r), axis=1)
    # img_crop_v = np.mean(img_crop, axis=1)

    # Use np.convolve to calculate the moving average
    # window_size = 5  # sliding windows for the moving average
    # moving_averages = np.convolve(
    #     img_crop_v, np.ones(window_size) / window_size, mode="valid"
    # )
    gradient_y = cv2.Sobel(img_crop, cv2.CV_64F, 0, 1, ksize=5)
    gradient_avgy = np.mean(gradient_y, axis=1)

    top = 0  # the index from cropped location instead of original image
    # ind = (
    #     np.argmin(moving_averages[200:-600]) + top + int(window_size / 2) + 200
    # )  # filter out the first 200 rows and last 100 rows
    start_filter_ind = 350  # 200 arab # crops is 350
    ind = (
        np.argmax(gradient_avgy[start_filter_ind:-550]) + top + start_filter_ind
    )  # filter out the first 200 rows and last 100 rows
    return ind


def get_layer_boundary_fodler(image_folder, save_path):
    images = [
        os.path.relpath(os.path.join(root, file), image_folder)
        for root, _, files in os.walk(image_folder)
        for file in files
        if (file.endswith(".PNG") or file.endswith(".png")) and not file.startswith(".")
    ]
    print(f"image_folder: {image_folder}")
    print(f"len images: {len(images)}")

    ind_df = pd.DataFrame()
    for img in images:
        image_name = os.path.join(image_folder, img)
        plant = os.path.dirname(image_name)
        frame = os.path.splitext(os.path.basename(image_name))[0]
        image = cv2.imread(image_name)

        ind = get_layer_boundary(image)
        ind_df = pd.concat(
            [
                ind_df,
                pd.DataFrame(
                    {
                        "image_name": [img],
                        "plant": [plant],
                        "frame": [frame],
                        "layer_ind": [ind],
                    }
                ),
            ],
            ignore_index=True,
        )
    csv_name = os.path.join(save_path, "layer_index.csv")
    print(f"csv_name: {csv_name}")
    ind_df.to_csv(csv_name, index=False)
    return ind_df


def get_area(seg_image, index_median, threshold_area):
    upper_layer = seg_image[170 : index_median - threshold_area, :, 0]
    value, count = np.unique(upper_layer[:, :], return_counts=True)
    upper_area = count[1] if len(count) > 1 else 0

    bottom_layer = seg_image[index_median + threshold_area : -5, :, 0]
    value, count = np.unique(bottom_layer[:, :], return_counts=True)
    bottom_area = count[1] if len(count) > 1 else 0
    return upper_area, bottom_area


def get_count(seg_image, index_median, threshold_area, threshold_count):
    upper_layer = seg_image[
        index_median - threshold_area - threshold_count : index_median - threshold_area,
        :,
        0,
    ]
    contours, stats = cv2.findContours(
        upper_layer, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if len(contours) > 0:
        contour_areas = [cv2.contourArea(contour) for contour in contours]
        upper_root_count = (
            len(contours)
            if np.max(contour_areas) < upper_layer.size
            else len(contours) - 1
        )
    else:
        upper_root_count = 0

    bottom_layer = seg_image[
        index_median + threshold_area : index_median + threshold_area + threshold_count,
        :,
        0,
    ]
    contours, stats = cv2.findContours(
        bottom_layer, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if len(contours) > 0:
        contour_areas = [cv2.contourArea(contour) for contour in contours]
        bottom_root_count = (
            len(contours)
            if np.max(contour_areas) < bottom_layer.size
            else len(contours) - 1
        )
    else:
        bottom_root_count = 0
    return upper_root_count, bottom_root_count


def get_statistics_frames(df_filtered, save_path):
    # import csv data
    # data_path = os.path.join(save_path, "traits_72frames.csv")
    # data = pd.read_csv(data_path)
    data = df_filtered

    # add ratio of root area and root count
    data["root_area_ratio"] = data["bottom_area"] / data["upper_area"]
    data["root_count_ratio"] = data["bottom_root_count"] / data["upper_root_count"]

    data = data[~data.isin([np.nan, np.inf, -np.inf]).any(axis=1)]
    # data["scanner_plant"] = data["scanner"] + "_" + data["plant"]

    # filter out outliers > 2
    z_score_threshold = 2
    filtered_df = pd.DataFrame()
    data_plant = data.groupby("plant")
    for name, group in data_plant:
        # Calculate the z-scores for 'root_count_ratio' and 'root_area_ratio' columns within each wave
        z_scores_count = np.abs(stats.zscore(group["root_count_ratio"]))
        z_scores_area = np.abs(stats.zscore(group["root_area_ratio"]))

        # Create boolean masks to filter out the outliers for each column
        outlier_mask_count = z_scores_count <= z_score_threshold
        outlier_mask_area = z_scores_area <= z_score_threshold

        # Combine the outlier masks for both columns using the logical AND operation
        combined_outlier_mask = outlier_mask_count & outlier_mask_area

        # Append the non-outlier rows to the filtered DataFrame
        filtered_df = pd.concat([filtered_df, group[combined_outlier_mask]])

    # filtered_df["trt"] = filtered_df["plant"].str[:2]
    filtered_df.to_csv(
        os.path.join(save_path, "traits_filteredframes.csv"), index=False
    )
    filtered_df_summary = (
        filtered_df.groupby("plant")[["root_area_ratio", "root_count_ratio"]]
        .mean()
        .reset_index()
    )
    filtered_df_summary.to_csv(
        os.path.join(save_path, "traits_filteredframes_summary.csv"), index=False
    )

    return filtered_df, filtered_df_summary


def get_statistics_plants(save_path):
    data_path = os.path.join(save_path, "traits_filteredframes_summary.csv")
    data = pd.read_csv(data_path)

    # get the data crop species, trt
    data[["sacnner", "plant"]] = data["scanner_plant"].str.split("_", expand=True)
    # data["crop_trt"] = data["crop"] + "_" + data["trt"]

    z_score_threshold = 2
    filtered_df = pd.DataFrame()
    data_plant = data.groupby("scanner_plant")
    for name, group in data_plant:
        # Calculate the z-scores for 'root_count_ratio' and 'root_area_ratio' columns within each wave
        z_scores_count = np.abs(stats.zscore(group["root_count_ratio"]))
        z_scores_area = np.abs(stats.zscore(group["root_area_ratio"]))

        # Create boolean masks to filter out the outliers for each column
        outlier_mask_count = z_scores_count <= z_score_threshold
        outlier_mask_area = z_scores_area <= z_score_threshold

        # Combine the outlier masks for both columns using the logical AND operation
        combined_outlier_mask = outlier_mask_count & outlier_mask_area

        # Append the non-outlier rows to the filtered DataFrame
        filtered_df = pd.concat([filtered_df, group[combined_outlier_mask]])
    filtered_df.to_csv(
        os.path.join(save_path, "traits_filteredplants.csv"), index=False
    )
    statistics = (
        filtered_df.groupby("scanner_plant")[["root_count_ratio", "root_area_ratio"]]
        .agg(["mean", "median", "std", "min", "max"])
        .reset_index()
    )
    statistics.to_csv(os.path.join(save_path, "scanner_plant_summary.csv"), index=False)

    return filtered_df, statistics


def viz_data(save_path):
    data_path = os.path.join(save_path, "traits_filteredplants.csv")
    data = pd.read_csv(data_path)

    # box plot of wave
    plt.figure(figsize=(10, 6))  # Optional: set the figure size
    sns.boxplot(x="crop_trt", y="root_count_ratio", hue="crop_trt", data=data)
    sns.stripplot(
        x="crop_trt",
        y="root_count_ratio",
        data=data,
        color="black",
        size=3,
        jitter=True,
    )
    plt.xticks(rotation=45)
    plt.savefig(os.path.join(save_path, "root_count_ratio.png"), bbox_inches="tight")

    plt.figure(figsize=(10, 6))  # Optional: set the figure size
    sns.boxplot(x="crop_trt", y="root_area_ratio", hue="crop_trt", data=data)
    sns.stripplot(
        x="crop_trt",
        y="root_area_ratio",
        data=data,
        color="black",
        size=3,
        jitter=True,
    )
    plt.xticks(rotation=45)
    plt.savefig(os.path.join(save_path, "root_area_ratio.png"), bbox_inches="tight")


def get_traits(seg_folder, ind_df, save_path):
    traits_df = ind_df
    for i in range(len(ind_df)):  #
        # print(f"Getting traits of {i+1}th image among {len(ind_df)} images")
        # get layer index and image path
        image_path = os.path.join(seg_folder, ind_df["image_name"][i])
        seg_image = cv2.imread(image_path)
        index_frame = int(ind_df["layer_ind"][i])

        # get areas
        threshold_area = 50
        upper_area, bottom_area = get_area(seg_image, index_frame, threshold_area)
        # get counts
        threshold_count = 5
        upper_root_count, bottom_root_count = get_count(
            seg_image, index_frame, threshold_area, threshold_count
        )
        traits_df.at[i, "upper_area"] = upper_area
        traits_df.at[i, "bottom_area"] = bottom_area
        traits_df.at[i, "upper_root_count"] = upper_root_count
        traits_df.at[i, "bottom_root_count"] = bottom_root_count
    save_name = os.path.join(save_path, "traits.csv")
    traits_df.to_csv(save_name, index=False)
    return traits_df


def remove_frame_outlier_0_upper(data, write_csv, output_dir):
    """Remove frames with 0 upper_root_count."""
    filter = data["upper_root_count"] == 0
    removed = data[filter]
    print(f"Removed {len(removed)} frames with 0 root count in upper layer")
    new_data = data[~filter]
    if write_csv:
        csv_path = os.path.join(output_dir, "removed_0upper.csv")
        removed.to_csv(csv_path, index=False)
    return new_data


def remove_frame_outlier_0_bottom(data, threshold, output_dir):
    """Remove outliers for less than 50% with 0 bottom_root_count."""
    # Group by 'plant' and calculate the percentage of frames with value 0
    frame_count_with_zeros = (
        data[data["bottom_root_count"] == 0].groupby("plant")["frame"].count()
    )
    total_frame_count = data.groupby("plant")["frame"].count()
    percentage_zeros = frame_count_with_zeros.div(total_frame_count, fill_value=0)

    # Get the plants where less than a threshold of frames have value 0
    plants_to_remove = percentage_zeros[percentage_zeros < threshold].index

    # Remove rows for the identified plants
    df_filtered = data[
        ~((data["plant"].isin(plants_to_remove)) & (data["bottom_root_count"] == 0))
    ]
    df_removed = data[
        ~(~((data["plant"].isin(plants_to_remove)) & (data["bottom_root_count"] == 0)))
    ]
    print(f"Removed {len(df_removed)} frames with less than 0.5 has 0 bottom counts")

    # save the filtered data
    filtered_path = os.path.join(output_dir, "filtered_72frames_0upper_0bottom.csv")
    df_filtered.to_csv(filtered_path, index=False)

    # save the removed data
    removed_path = os.path.join(output_dir, "removed_0bottom.csv")
    df_removed.to_csv(removed_path, index=False)
    return df_filtered, df_removed


def main():
    parser = argparse.ArgumentParser(
        description="Traits extraction and analysis Pipeline"
    )
    parser.add_argument("--image_folder", required=True, help="original image path")
    parser.add_argument("--seg_folder", required=True, help="Segmentation path")
    parser.add_argument(
        "--save_path", required=True, help="Traits and analysis save path"
    )

    args = parser.parse_args()

    image_folder = args.image_folder
    seg_folder = args.seg_folder
    save_path = args.save_path

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    # get the layer index of each cropped image
    print("Getting layer boundary index")
    ind_df = get_layer_boundary_fodler(image_folder, save_path)
    ind_df = pd.read_csv(os.path.join(save_path, "layer_index.csv"))
    print(f"ind_df columns: {ind_df.columns}")

    # boundary_idx_72frames = get_layer_boundary_folder(image_folder, seg_folder)
    # boundary_idx_72frames.to_csv(
    #     os.path.join(save_path, "traits_72frames.csv"), index=False
    # )

    # get traits
    print("Getting traits")
    traits_df = get_traits(seg_folder, ind_df, save_path)
    # traits_df = pd.read_csv(os.path.join(save_path, "traits.csv"))

    # delete frames with 0 in upper layer
    write_csv = True  # save the filtered data
    remove_0 = remove_frame_outlier_0_upper(traits_df, write_csv, save_path)

    # remove outliers for less than a threshold with 0 bottom_root_count.
    # the default threshold is 50% (0.5)
    # CHANGE the threshold if needed
    threshold = 0.5
    df_filtered, df_removed = remove_frame_outlier_0_bottom(
        remove_0, threshold, save_path
    )
    # df_filtered = pd.read_csv(
    #     os.path.join(save_path, "filtered_72frames_0upper_0bottom.csv")
    # )

    filtered_df_frames, filtered_df_summary_frames = get_statistics_frames(
        df_filtered, save_path
    )

    # filtered_df_plant = get_statistics_plants(save_path)
    # viz_data(save_path)


if __name__ == "__main__":
    main()
