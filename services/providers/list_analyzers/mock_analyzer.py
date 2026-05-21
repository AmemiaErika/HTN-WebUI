from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer


class MockListAnalyzer(BaseListAnalyzer):
    name = "mock"

    def analyze_objects(self, image_path: str) -> dict:
        return {
            "provider": self.name,
            "objects": [
                {
                    "name": "主角玩偶",
                    "description": "画面中心偏前方的橙黑配色潮玩角色，圆头大眼，猪鼻造型，穿黑色外套，身体短小，表面有塑料玩具质感。"
                },
                {
                    "name": "透明展示盒",
                    "description": "包围主角的透明方形展示罩，边缘有高光反射，整体像亚克力或透明塑料材质，位于画面中央后方。"
                },
                {
                    "name": "礼物盒装饰",
                    "description": "画面周围的彩色礼盒与小型装饰物，主要分布在左右和前景位置，方盒结构，带亮色包装和卡通装饰。"
                }
            ]
        }
