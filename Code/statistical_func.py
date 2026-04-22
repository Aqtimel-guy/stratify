##########################
# Import necessary libraries
##########################

import random
import numpy as np

##########################
# STATISTICAL FUNCTIONS
##########################




def avg(list1):
    ### Calculates the average of a list of numbers
    if not list1:
        raise ValueError("List is empty")
    return sum(list1) / len(list1)


def median(list1):
    """Calculates the median of a list of numbers."""
    sorted_list = sorted(list1)
    n = len(sorted_list)
    if n % 2 == 0:
        return (sorted_list[n // 2 - 1] + sorted_list[n // 2]) / 2
    else:
        return sorted_list[n // 2]

def variance(list1):
    """Calculates the variance of a list of numbers."""
    mean = avg(list1)
    return sum((x - mean)**2 for x in list1) / len(list1)

def std_dev(list1):
    """Calculates the standard deviation of a list of numbers."""
    return variance(list1) ** 0.5

def r_correlation(list1, list2):
    """Calculates the correlation coefficient between two lists."""
    if len(list1) != len(list2):
        raise ValueError("Lists must be of the same length")
    mean1 = avg(list1)
    mean2 = avg(list2)
    numerator = sum((x - mean1) * (y - mean2) for x, y in zip(list1, list2))
    denominator = std_dev(list1) * std_dev(list2) * len(list1)
    if denominator == 0:
        raise ValueError("Standard deviation is zero; correlation undefined")
    return numerator / denominator

def linear_regression(list1, list2, x):
    """Predicts y using linear regression on two lists of numbers."""
    if len(list1) != len(list2):
        raise ValueError("Lists must be of the same length")
    mean_x = avg(list1)
    mean_y = avg(list2)
    slope_m = r_correlation(list1, list2) * (std_dev(list2) / std_dev(list1))
    return mean_y + slope_m * (x - mean_x)

def r_squared(y_true, y_pred):
    """Calculates the R-squared value between two lists of numbers."""
    if len(y_pred) != len(y_true):
        raise ValueError("Lists must be of the same length")
    mean_y = avg(y_true)
    ss_total = sum((y - mean_y) ** 2 for y in y_true)
    ss_residual = sum((y_true[i] - y_pred[i]) ** 2 for i in range(len(y_true)))
    if ss_total == 0:
        raise ValueError("R-squared undefined when all true values are the same")
    return 1 - (ss_residual / ss_total)

##########################
# CLUSTERING FUNCTIONS
##########################

def k_mean(list1, k):
    """Performs k-means clustering for a list of numbers."""
    if not list1:
        raise ValueError("List must not be empty")
    if k <= 0 or k > len(list1):
        raise ValueError("k must be a positive integer <= length of the list")

    # Initialize centroids randomly
    centroids = random.sample(list1, k)

    while True:
        clusters = {i: [] for i in range(k)}
        for x in list1:
            closest_centroid = min(range(k), key=lambda i: abs(x - centroids[i]))
            clusters[closest_centroid].append(x)

        new_centroids = [avg(clusters[i]) if clusters[i] else centroids[i] for i in range(k)]

        # Check for convergence
        if all(abs(new_centroids[i] - centroids[i]) < 1e-6 for i in range(k)):
            break

        centroids = new_centroids

    return clusters, centroids

def find_optimal_k(clients, threshold):
    """Finds a sufficient number of clusters (k) for k-means using average std deviation within threshold."""
    k = 1
    avg_st_dv = threshold + 1  # start above threshold

    while avg_st_dv > threshold and k <= len(clients):
        clusters, _ = k_mean([spending for _, spending in clients], k)
        avg_st_dv = sum(std_dev(group) for group in clusters.values()) / k
        k += 1

    return k - 1




    print(f"Group {i}: {len(group)} clients, centroid: {avg(group):.2f}, std dev: {std_dev(group):.2f}")