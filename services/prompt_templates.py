from services.prompt_store import get_prompt_template, render_template


def object_list_prompt() -> str:
    return get_prompt_template("object_list")


def three_view_prompt(object_name: str, object_description: str) -> str:
    return render_template(
        get_prompt_template("three_view"),
        {
            "object_name": object_name,
            "object_description": object_description,
        },
    )


def compose_prompt(composition_prompt: str, env_options: dict) -> str:
    return render_template(
        get_prompt_template("compose"),
        {
            "composition_prompt": composition_prompt,
            "time": env_options.get("time", "白天"),
            "lighting": env_options.get("lighting", "柔光"),
            "weather": env_options.get("weather", "晴天"),
            "style": env_options.get("style", "潮玩概念设计"),
            "camera": env_options.get("camera", "产品摄影视角"),
        },
    )


def sketch_refine_prompt(refine_prompt: str) -> str:
    return render_template(
        get_prompt_template("sketch_refine"),
        {
            "refine_prompt": refine_prompt,
        },
    )
