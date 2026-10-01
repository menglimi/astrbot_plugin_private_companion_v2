# 游戏纯规则切片

更新时间：2026-09-26。实现位于 `companion_v2/games/`，核心可在没有 AstrBot SDK 的进程中导入。

本切片迁移井字棋、自由规则五子棋、贪心骰子和二十一点的内存状态与纯计算规则，包括合法落子、胜负/平局、悔棋、有限 Bot 决策、骰子暂存/收分与二十一点计分/庄家策略/结算。可预测的发牌和掷骰接口供合成测试使用。

不包含房间、玩家身份或席位、AstrBot/QQ、对话提示词、真实发送、活动占用、持久化、记忆来源及旧数据。五子棋 WebUI 拖拽特例不属于核心规则。后续业务接入需单独确定 target、授权、活动正本、结果来源和记忆合同。

定向验收：`tests/test_games_tictactoe.py`、`test_games_gomoku.py`、`test_games_pig_dice.py`、`test_games_blackjack.py`。测试使用合成棋盘、牌序和掷骰值。
