from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer


class MockListAnalyzer(BaseListAnalyzer):
    name = "mock"

    def analyze_objects(self, image_path: str, prompt_text: str | None = None) -> dict:
        prompt = prompt_text or ""
        if "细节元素" in prompt or "按钮" in prompt or "小型视觉元素" in prompt:
            objects = [
                {
                    "id": 1,
                    "name": "红色圆形按钮",
                    "description": "位于主体正面偏上方的红色圆形按钮，边缘有灰色结构包围，是明显的小型操作元素。",
                    "position": "主体正面上方偏左",
                    "bbox": [0.31, 0.30, 0.40, 0.39],
                    "level": "detail",
                },
                {
                    "id": 2,
                    "name": "绿色频谱屏幕",
                    "description": "主体正面中央偏下的长方形绿色发光频谱显示屏，黑色边框，内部有跳动条形图案。",
                    "position": "主体正面中下方",
                    "bbox": [0.20, 0.48, 0.55, 0.62],
                    "level": "detail",
                },
            ]
        elif "主要部件" in prompt or "大型部件" in prompt or "拆分其中" in prompt:
            objects = [
                {
                    "id": 1,
                    "name": "黄色顶部提手",
                    "description": "位于播放器顶部的黄色可折叠提手，长条弧形结构，带黑色纹理和工业风边线。",
                    "position": "主体顶部",
                    "bbox": [0.38, 0.08, 0.76, 0.23],
                    "level": "part",
                },
                {
                    "id": 2,
                    "name": "正面控制面板",
                    "description": "播放器正面的大面积深色控制区域，包含按钮组、绿色显示屏和黑色面板结构。",
                    "position": "主体正面中央",
                    "bbox": [0.14, 0.31, 0.70, 0.65],
                    "level": "part",
                },
            ]
        else:
            objects = [
                {
                    "id": 1,
                    "name": "复古播放器主体",
                    "description": "米白色和深灰色为主的方正复古播放器，带黄色顶部提手、黑色控制面板和绿色频谱屏幕。",
                    "position": "画面中央偏上",
                    "bbox": [0.12, 0.12, 0.76, 0.74],
                    "level": "object",
                },
                {
                    "id": 2,
                    "name": "黄色磁带",
                    "description": "左下角的黄色透明磁带，扁平方形结构，有两个白色圆形磁带轴和蓝色标签文字。",
                    "position": "画面左下角",
                    "bbox": [0.04, 0.61, 0.35, 0.96],
                    "level": "object",
                },
                {
                    "id": 3,
                    "name": "奶酪形装饰物",
                    "description": "右下角的黄色奶酪形小道具，三角块状结构，表面有圆孔。",
                    "position": "画面右下角",
                    "bbox": [0.52, 0.70, 0.76, 0.95],
                    "level": "object",
                },
            ]
        return {"provider": self.name, "objects": objects}
