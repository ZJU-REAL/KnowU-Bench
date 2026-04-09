import re


def bounds_to_coords(bounds_string):
    pattern = r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"
    matches = re.findall(pattern, bounds_string)
    return list(map(int, matches[0]))


def coords_to_bounds(bounds):
    return f"[{bounds[0]},{bounds[1]}][{bounds[2]},{bounds[3]}]"


def check_valid_bounds(bounds):
    bounds = bounds_to_coords(bounds)

    return bounds[0] >= 0 and bounds[1] >= 0 and bounds[0] < bounds[2] and bounds[1] < bounds[3]


def check_bounds_containing(bounds_contained, bounds_containing):
    bounds_contained = bounds_to_coords(bounds_contained)
    bounds_containing = bounds_to_coords(bounds_containing)

    return (
        bounds_contained[0] >= bounds_containing[0]
        and bounds_contained[1] >= bounds_containing[1]
        and bounds_contained[2] <= bounds_containing[2]
        and bounds_contained[3] <= bounds_containing[3]
    )


def check_bounds_intersection(bounds1, bounds2):
    bounds1 = bounds_to_coords(bounds1)
    bounds2 = bounds_to_coords(bounds2)

    return (
        bounds1[0] < bounds2[2]
        and bounds1[2] > bounds2[0]
        and bounds1[1] < bounds2[3]
        and bounds1[3] > bounds2[1]
    )
