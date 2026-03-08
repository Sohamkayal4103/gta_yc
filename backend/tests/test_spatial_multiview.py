from backend.agents.spatial_analyst import _merge_view_layouts


def test_merge_view_layouts_combines_objects_and_descriptions():
    front_layout = {
        "room_width_meters": 4.0,
        "room_height_meters": 5.0,
        "objects": [
            {
                "name": "Desk",
                "object_type": "furniture",
                "x_percent": 0.2,
                "y_percent": 0.4,
                "width_percent": 0.2,
                "height_percent": 0.1,
                "is_interactable": True,
                "description": "Wood desk",
            }
        ],
        "walls": [
            {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.0},
            {"x1": 1.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},
            {"x1": 0.0, "y1": 1.0, "x2": 1.0, "y2": 1.0},
            {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 1.0},
        ],
        "door_positions": [{"x_percent": 0.5, "y_percent": 1.0}],
        "lighting": "natural",
        "floor_type": "hardwood",
        "_room_description_detailed": "Front view description.",
    }
    left_layout = {
        "room_width_meters": 4.2,
        "room_height_meters": 5.1,
        "objects": [
            {
                "name": "Desk",
                "object_type": "furniture",
                "x_percent": 0.25,
                "y_percent": 0.45,
                "width_percent": 0.2,
                "height_percent": 0.1,
                "is_interactable": False,
                "description": "Desk from left angle",
            },
            {
                "name": "Bookshelf",
                "object_type": "storage",
                "x_percent": 0.75,
                "y_percent": 0.2,
                "width_percent": 0.15,
                "height_percent": 0.3,
                "is_interactable": True,
                "description": "Tall shelf",
            },
        ],
        "walls": front_layout["walls"],
        "door_positions": [{"x_percent": 0.5, "y_percent": 1.0}],
        "lighting": "natural",
        "floor_type": "hardwood",
        "_room_description_detailed": "Left view description.",
    }

    merged = _merge_view_layouts({"front": front_layout, "left": left_layout})

    assert merged["room_width_meters"] > 4.0
    assert merged["room_height_meters"] > 5.0
    assert len(merged["objects"]) == 2
    assert "FRONT VIEW" in merged["_room_description_detailed"]
    assert "LEFT VIEW" in merged["_room_description_detailed"]
    assert "front" in merged["_view_descriptions"]
    assert "left" in merged["_view_descriptions"]
