(() => {
  "use strict";

  const token = decodeURIComponent(window.location.pathname.split("/")[2] || "");
  const $ = (id) => document.getElementById(id);
  const labels = {
    tictactoe: "井字棋", gomoku: "五子棋", xiangqi: "中国象棋", pig_dice: "掷骰竞分",
    blackjack: "二十一点", turtle_soup: "海龟汤", draw_guess: "你画我猜",
  };
  const stateLabel = {active: "对局进行中", finished: "本局结束", closed: "已关闭"};
  let game = null;
  let timer = 0;
  let busy = false;
  let selected = null;
  let selectedPiece = null;
  let dragState = null;
  let dragClickGuardUntil = 0;
  let requestSequence = 0;
  let loading = false;
  let renderedSignature = "";
  const gomoku = window.CompanionGomokuRoom.create({node, $, getGame: () => game,
    isBusy: () => busy, getSelectedPiece: () => selectedPiece,
    clearSelectedPiece: () => { selectedPiece = null; },
    setSelectedPiece: source => { selectedPiece = source; },
    sendAction, render, setNotice, refreshControls: () => renderControls(game.state || {})});

  function node(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== "") element.textContent = text;
    return element;
  }

  function iconButton(icon, label, action, className = "") {
    const button = node("button", `control-button ${className}`.trim());
    button.type = "button";
    button.innerHTML = `<i data-lucide="${icon}" aria-hidden="true"></i><span>${label}</span>`;
    button.disabled = busy || game?.status !== "active";
    button.addEventListener("click", () => sendAction(action));
    return button;
  }

  function paintIcons() {
    if (window.lucide?.createIcons) window.lucide.createIcons();
  }

  function setNotice(message, error = false) {
    $("notice").textContent = message || "";
    $("notice").classList.toggle("error", error);
  }

  function turnIsHuman(state) {
    if (game?.game_type === "xiangqi") return state.turn === state.human_side;
    if (["tictactoe", "gomoku"].includes(game?.game_type)) {
      return state.turn === (state.human_mark ?? state.human_color);
    }
    return state.turn === "human" || !state.turn;
  }

  function boardSize(kind) {
    return kind === "gomoku" ? 15 : 3;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function pointerTarget(event, stage, size) {
    const rect = stage.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.left + rect.width
        || event.clientY < rect.top || event.clientY > rect.top + rect.height) return null;
    const boardX = clamp((event.clientX - rect.left) / rect.width, 0, .999999);
    const boardY = clamp((event.clientY - rect.top) / rect.height, 0, .999999);
    const column = Math.min(size - 1, Math.floor(boardX * size));
    const row = Math.min(size - 1, Math.floor(boardY * size));
    if (game.game_type === "gomoku") return {row, column, x: .5, y: .5};
    return {
      row,
      column,
      x: Number(clamp(boardX * size - column, .02, .98).toFixed(4)),
      y: Number(clamp(boardY * size - row, .02, .98).toFixed(4)),
    };
  }

  function cellTarget(event, cell, row, column) {
    const rect = cell.getBoundingClientRect();
    return {
      row,
      column,
      x: Number(clamp((event.clientX - rect.left) / rect.width, .02, .98).toFixed(4)),
      y: Number(clamp((event.clientY - rect.top) / rect.height, .02, .98).toFixed(4)),
    };
  }

  function pieceSource(piece) {
    return {kind: "board", piece_id: piece.piece_id, color: piece.color};
  }

  function selectPiece(source) {
    if (busy || game?.status !== "active" || Date.now() < dragClickGuardUntil) return;
    selectedPiece = source;
    setNotice(source.kind === "tray" ? "已取子，点击棋盘落点" : "已拿起棋子，点击新的落点");
    render();
  }

  function pieceVisual(element, color, kind, human) {
    element.classList.add(color === human ? "piece-player" : "piece-bot");
    if (kind === "gomoku") {
      element.appendChild(node("span", `stone ${color === 1 ? "stone-black" : "stone-white"}`));
    } else {
      element.textContent = color === human ? "×" : "○";
    }
  }

  function beginPiecePointer(event, source, element) {
    if (busy || game?.status !== "active") return;
    const stage = $("gameBoard").querySelector(".gomoku-intersections")
      || $("gameBoard").querySelector(".board-stage");
    if (!stage) return;
    event.preventDefault();
    const ghost = node("div", "drag-ghost");
    pieceVisual(ghost, source.color, game.game_type, game.state.human_mark ?? game.state.human_color);
    stage.appendChild(ghost);
    const stageRect = stage.getBoundingClientRect();
    ghost.style.left = `${clamp(event.clientX - stageRect.left, 0, stageRect.width)}px`;
    ghost.style.top = `${clamp(event.clientY - stageRect.top, 0, stageRect.height)}px`;
    const startX = event.clientX;
    const startY = event.clientY;
    dragState = {source, stage, ghost, pointerId: event.pointerId,
      startX, startY, moved: false};
    const move = (moveEvent) => {
      if (!dragState || moveEvent.pointerId !== dragState.pointerId) return;
      const distance = Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY);
      if (distance > 5) dragState.moved = true;
      const rect = stage.getBoundingClientRect();
      ghost.style.left = `${clamp(moveEvent.clientX - rect.left, 0, rect.width)}px`;
      ghost.style.top = `${clamp(moveEvent.clientY - rect.top, 0, rect.height)}px`;
    };
    const finish = (finishEvent) => {
      if (!dragState || finishEvent.pointerId !== dragState.pointerId) return;
      const current = dragState;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
      current.ghost.remove();
      dragState = null;
      if (!current.moved) {
        selectPiece(source);
        return;
      }
      dragClickGuardUntil = Date.now() + 260;
      const target = pointerTarget(finishEvent, current.stage, boardSize(game.game_type));
      if (!target) { setNotice("已取消拖动，棋子未移动"); return; }
      sendAction({action: "interact", source,
        target,
        interaction: "drag"});
    };
    const cancel = (cancelEvent) => {
      if (!dragState || cancelEvent.pointerId !== dragState.pointerId) return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
      dragState.ghost.remove();
      dragState = null;
    };
    window.addEventListener("pointermove", move, {passive: false});
    window.addEventListener("pointerup", finish, {passive: false});
    window.addEventListener("pointercancel", cancel, {passive: false});
  }

  function boardPiece(piece, state, kind, size) {
    const human = state.human_mark ?? state.human_color;
    const element = node("button", "floating-piece");
    element.type = "button";
    element.dataset.pieceId = piece.piece_id;
    element.setAttribute("aria-label", `${piece.color === human ? "你的" : "Bot 的"}棋子，可拖动`);
    element.style.left = `${((piece.column + piece.x) / size) * 100}%`;
    element.style.top = `${((piece.row + piece.y) / size) * 100}%`;
    pieceVisual(element, piece.color, kind, human);
    if (selectedPiece?.kind === "board" && selectedPiece.piece_id === piece.piece_id) {
      element.classList.add("selected");
    }
    element.addEventListener("pointerdown", (event) => beginPiecePointer(event, pieceSource(piece), element));
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      if (Date.now() < dragClickGuardUntil) return;
      selectPiece(pieceSource(piece));
    });
    return element;
  }

  function renderGridBoard(board, kind, state) {
    const size = boardSize(kind);
    const stage = node("div", `board-stage ${kind === "gomoku" ? "gomoku-stage" : "tictactoe-stage"}`);
    stage.style.setProperty("--board-size", size);
    const grid = node("div", `grid-board board-grid ${kind === "gomoku" ? "gomoku-board" : "tictactoe-board"}`);
    const human = state.human_mark ?? state.human_color;
    const bot = state.bot_mark ?? state.bot_color;
    grid.style.gridTemplateColumns = `repeat(${board.length || 3}, minmax(0, 1fr))`;
    board.forEach((row, rowIndex) => row.forEach((cell, columnIndex) => {
      const button = node("button", "board-cell");
      button.type = "button";
      button.setAttribute("aria-label", `第 ${rowIndex + 1} 行，第 ${columnIndex + 1} 列`);
      const empty = cell === 0 || cell === null || cell === "" || cell === ".";
      if (!empty && kind === "gomoku") {
        button.classList.add("logical-occupied");
      } else if (!empty) {
        button.classList.add("logical-occupied");
      }
      const canMove = !busy && game.status === "active" && empty
        && (selectedPiece || turnIsHuman(state));
      button.disabled = !canMove;
      button.addEventListener("click", (event) => {
        if (!empty) return;
        const target = cellTarget(event, button, rowIndex, columnIndex);
        if (selectedPiece) {
          const source = selectedPiece;
          selectedPiece = null;
          sendAction({action: "interact", source, target, interaction: "click"});
        } else if (turnIsHuman(state)) {
          sendAction({action: "move", ...target});
        }
      });
      grid.appendChild(button);
    }));
    stage.appendChild(grid);
    const layer = node("div", "piece-layer");
    (Array.isArray(state.pieces) ? state.pieces : []).forEach((piece) => {
      layer.appendChild(boardPiece(piece, state, kind, size));
    });
    stage.appendChild(layer);
    $("gameBoard").appendChild(stage);
  }

  function renderPieceTray(state) {
    if (game.game_type === "gomoku") { gomoku.renderTray(state); return; }
    const tray = $("pieceTray");
    tray.replaceChildren();
    const isBoardGame = ["tictactoe", "gomoku"].includes(game.game_type);
    tray.hidden = !isBoardGame || game.status !== "active";
    if (!isBoardGame || game.status !== "active") return;
    tray.append(node("div", "piece-tray-heading", "棋盒"));
    const human = state.human_mark ?? state.human_color;
    [[human, "你的棋"], [state.bot_mark ?? state.bot_color, "Bot 的棋"]].forEach(([color, label]) => {
      const piece = node("button", "tray-piece");
      piece.type = "button";
      piece.setAttribute("aria-label", `${label}，点击或拖动到棋盘`);
      piece.title = `${label} · 点击后选择落点`;
      pieceVisual(piece, color, game.game_type, human);
      if (selectedPiece?.kind === "tray" && selectedPiece.color === color) piece.classList.add("selected");
      const source = {kind: "tray", color};
      piece.addEventListener("pointerdown", (event) => beginPiecePointer(event, source, piece));
      piece.addEventListener("click", (event) => {
        event.stopPropagation();
        if (Date.now() < dragClickGuardUntil) return;
        selectPiece(source);
      });
      tray.appendChild(piece);
    });
    tray.append(node("span", "piece-tray-hint", selectedPiece ? "选择棋盘落点" : "双方棋子均可拿起"));
  }

  const pieces = {
    r: "車", n: "馬", b: "象", a: "士", k: "將", c: "砲", p: "卒",
    R: "車", N: "馬", B: "相", A: "仕", K: "帥", C: "炮", P: "兵",
  };

  function renderXiangqi(state) {
    const board = node("div", "xiangqi-board");
    const legal = Array.isArray(state.legal_moves) ? state.legal_moves : [];
    const active = game.status === "active" && turnIsHuman(state) && !busy;
    state.board.forEach((row, rowIndex) => row.forEach((piece, columnIndex) => {
      const button = node("button", "xiangqi-cell");
      button.type = "button";
      button.textContent = pieces[piece] || "";
      if (piece && piece !== ".") button.classList.add(piece === piece.toUpperCase() ? "piece-red" : "piece-black");
      button.setAttribute("aria-label", `${rowIndex + 1} 行 ${columnIndex + 1} 列${pieces[piece] ? ` ${pieces[piece]}` : " 空位"}`);
      const isSelected = selected?.[0] === rowIndex && selected?.[1] === columnIndex;
      if (isSelected) button.classList.add("selected");
      button.disabled = !active;
      button.addEventListener("click", () => {
        if (!selected) {
          if (legal.some((move) => move[0] === rowIndex && move[1] === columnIndex)) {
            selected = [rowIndex, columnIndex];
            render();
          }
          return;
        }
        const move = legal.find((item) => item[0] === selected[0] && item[1] === selected[1]
          && item[2] === rowIndex && item[3] === columnIndex);
        if (move) {
          selected = null;
          sendAction({action: "move", from_row: move[0], from_column: move[1], to_row: move[2], to_column: move[3]});
        } else if (legal.some((item) => item[0] === rowIndex && item[1] === columnIndex)) {
          selected = [rowIndex, columnIndex];
          render();
        } else {
          selected = null;
          render();
        }
      });
      board.appendChild(button);
    }));
    $("gameBoard").appendChild(board);
  }

  function scoreItem(label, value, type = "") {
    const item = node("div", `score-item ${type}`.trim());
    item.append(node("small", "", label), node("strong", "", String(value)));
    return item;
  }

  function renderSummary(state) {
    const summary = $("gameSummary");
    summary.replaceChildren();
    if (game.game_type === "tictactoe" || game.game_type === "gomoku") {
      const pair = node("div", "score-pair");
      const isGomoku = game.game_type === "gomoku";
      pair.append(scoreItem("你", isGomoku ? (state.human_color === 1 ? "黑棋" : "白棋") : "×", "player"));
      pair.append(scoreItem("陪伴者", isGomoku ? (state.bot_color === 1 ? "黑棋" : "白棋") : "○", "bot"));
      const phase = game.status !== "active" ? stateLabel[game.status]
        : (isGomoku ? gomoku.phase() : (turnIsHuman(state) ? "轮到你了" : "对方思考中"));
      summary.append(pair, node("p", "summary-line", `已落子 ${state.move_count || 0} 手 · ${phase}`));
      if (isGomoku && state.last_move) summary.append(node("p", "summary-line", `最后一手：第 ${state.last_move[0] + 1} 行，第 ${state.last_move[1] + 1} 列`));
    } else if (game.game_type === "pig_dice") {
      const pair = node("div", "score-pair");
      pair.append(scoreItem("你", state.human_score, "player"), scoreItem("陪伴者", state.bot_score, "bot"));
      summary.append(pair, node("p", "summary-line", `当前回合 ${state.turn_total} 分 · ${state.target_score} 分获胜`));
    } else if (game.game_type === "blackjack") {
      const hand = state.hands?.["1"];
      const pair = node("div", "score-pair");
      pair.append(scoreItem("你的点数", hand?.value ?? 0, "player"), scoreItem("庄家点数", state.dealer_total ?? 0, "bot"));
      summary.append(pair, node("p", "summary-line", state.dealer_hidden ? "庄家底牌暂时盖住" : (state.phase === "dealer_turn" ? "庄家正在补牌" : "无下注单人对局")));
    } else if (game.game_type === "xiangqi") {
      const pair = node("div", "score-pair");
      pair.append(scoreItem("你执", state.human_side === "red" ? "红" : "黑", "player"), scoreItem("已走", state.move_count || 0, "bot"));
      summary.append(pair, node("p", "summary-line", game.status === "active"
        ? (turnIsHuman(state) ? "轮到你落子" : "对方正在应手") : stateLabel[game.status]));
    } else if (game.game_type === "turtle_soup") {
      const pair = node("div", "score-pair");
      pair.append(scoreItem("已提问", state.question_count || 0, "player"), scoreItem("已发现", `${state.discovered_fact_count || 0}/${state.key_fact_count || 0}`, "bot"));
      summary.append(pair, node("p", "summary-line", `提示 ${state.hints_used || 0} / ${state.hint_limit || 0}`));
    } else if (game.game_type === "draw_guess") {
      const pair = node("div", "score-pair");
      pair.append(scoreItem("已猜", state.guess_count || 0, "player"), scoreItem("还可猜", Math.max(0, (state.max_guesses || 0) - (state.guess_count || 0)), "bot"));
      summary.append(pair, node("p", "summary-line", `剩余 ${state.remaining_seconds ?? 0} 秒`));
    }
    if (game.status === "finished") {
      const isPuzzle = ["turtle_soup", "draw_guess"].includes(game.game_type);
      const result = isPuzzle ? (game.outcome === "player" ? "你解答成功了" : "本局未解答成功")
        : ({player: "你赢了", bot: "陪伴者赢了", draw: "本局平局"}[game.outcome] || "本局结束");
      summary.append(node("p", "summary-line game-outcome", result));
    }
  }

  function cardMarkup(card) {
    const suits = {spades: "♠", clubs: "♣", hearts: "♥", diamonds: "♦"};
    const suit = suits[card.suit] || card.suit || "";
    const element = node("div", `playing-card ${["hearts", "diamonds"].includes(card.suit) ? "red" : ""}`.trim());
    element.append(node("strong", "", String(card.rank)), node("small", "", suit));
    return element;
  }

  function renderBlackjack(state) {
    const table = node("div", "blackjack-table");
    const dealer = node("div", "hand-zone");
    dealer.append(node("span", "hand-label", `庄家${state.dealer_hidden ? " · 暗牌" : ` · ${state.dealer_total} 点`}`));
    const dealerCards = node("div", "cards");
    (state.dealer_cards || []).forEach((card) => dealerCards.append(cardMarkup(card)));
    if (state.dealer_hidden) dealerCards.append(node("div", "playing-card", "?"));
    dealer.append(dealerCards);
    const player = node("div", "hand-zone");
    const hand = state.hands?.["1"];
    player.append(node("span", "hand-label", `你 · ${hand?.value ?? 0} 点`));
    const playerCards = node("div", "cards");
    (hand?.cards || []).forEach((card) => playerCards.append(cardMarkup(card)));
    player.append(playerCards);
    table.append(dealer, player);
    $("gameBoard").appendChild(table);
  }

  function renderBoard(state) {
    const host = $("gameBoard");
    host.replaceChildren();
    host.setAttribute("aria-busy", "false");
    if (game.game_type === "gomoku") {
      gomoku.renderBoard(state);
    } else if (game.game_type === "tictactoe") {
      renderGridBoard(state.board || [], game.game_type, state);
    } else if (game.game_type === "xiangqi") {
      renderXiangqi(state);
    } else if (game.game_type === "pig_dice") {
      const dice = node("div", "dice-layout");
      const face = state.last_roll?.final ?? state.last_roll ?? "·";
      dice.append(node("div", "die", String(face)), node("p", "summary-line", `本回合 ${state.turn_total || 0} 分 · ${state.turn === "human" ? "轮到你" : "对方掷骰中"}`));
      host.appendChild(dice);
    } else if (game.game_type === "blackjack") {
      renderBlackjack(state);
    } else if (game.game_type === "turtle_soup") {
      const surface = node("article", "soup-surface");
      surface.append(node("h2", "题面"), node("p", "", state.puzzle?.surface || "题面暂不可用"));
      if (state.puzzle?.solution) surface.append(node("p", "summary-line", `汤底：${state.puzzle.solution}`));
      host.appendChild(surface);
    } else if (game.game_type === "draw_guess") {
      const guesses = Array.isArray(state.guesses) ? state.guesses : [];
      const list = node("div", "soup-surface");
      list.append(node("h2", "你的猜测"));
      list.append(node("p", "", guesses.length ? guesses.map((item) => `${item.guess}${item.correct ? " · 猜中" : " · 未命中"}`).join("\n") : "还没有猜测"));
      host.appendChild(list);
    }
    renderSummary(state);
  }

  function renderControls(state) {
    const controls = $("actionControls");
    controls.replaceChildren();
    if (game.status === "active") {
      if (game.game_type === "gomoku") {
        gomoku.renderControls(controls, state);
      } else if (game.game_type === "pig_dice") {
        controls.append(iconButton("dices", "桌面掷骰", {action: "roll"}, "primary"));
        controls.append(iconButton("glass-water", "推骰盅", {action: "roll", method: "cup"}));
        controls.append(iconButton("save", "存下分数", {action: "hold"}));
      } else if (game.game_type === "blackjack") {
        controls.append(iconButton("plus", "再要一张", {action: "hit"}, "primary"));
        controls.append(iconButton("hand", "停牌", {action: "stand"}));
      } else if (game.game_type === "turtle_soup") {
        controls.append(iconButton("lightbulb", "给我一点提示", {action: "hint"}));
        controls.append(iconButton("flag", "揭晓汤底", {action: "give_up"}, "warm"));
      } else if (game.game_type === "draw_guess") {
        const form = node("form", "guess-form");
        const input = node("input");
        input.name = "guess";
        input.maxLength = 80;
        input.autocomplete = "off";
        input.placeholder = "输入你的猜测";
        input.setAttribute("aria-label", "输入你的猜测");
        const button = node("button", "control-button primary");
        button.type = "submit";
        button.innerHTML = '<i data-lucide="send" aria-hidden="true"></i><span>提交</span>';
        button.disabled = busy;
        form.append(input, button);
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const guess = input.value.trim();
          if (guess) sendAction({action: "guess", guess});
        });
        controls.appendChild(form);
        controls.append(iconButton("flag", "放弃本局", {action: "give_up"}, "warm"));
      } else if (game.game_type === "xiangqi") {
        controls.append(node("p", "summary-line", selected ? "选择要移动到的位置" : "点击红方棋子开始选择"));
      }
    }
    if (game.status === "active") controls.append(iconButton("x", "结束对局", {action: "close"}, "warm"));
    if (game.game_type === "turtle_soup" && game.status === "active") {
      controls.append(node("span", "summary-line", "提问与推理继续在聊天中进行"));
    }
    paintIcons();
  }

  function renderHistory() {
    const list = $("gameHistory");
    list.replaceChildren();
    const events = game.events || game.moves || [];
    $("actionCount").textContent = String(events.length);
    events.slice(-8).reverse().forEach((event, index) => {
      let action = "落子";
      let actor = `第 ${events.length - index} 手`;
      if (Array.isArray(event)) {
        if (["tictactoe", "gomoku"].includes(game.game_type)) {
          actor = event[2] === (game.state.human_mark ?? game.state.human_color) ? "你" : "陪伴者";
          action = `第 ${event[0] + 1} 行，第 ${event[1] + 1} 列`;
        } else {
          actor = event[0] === "human" ? "你" : "陪伴者";
          action = event[1] === "cup_roll" ? `骰盅 ${event[2]?.[0]} → ${event[2]?.[1]}`
            : event[1] === "roll" ? `掷出 ${event[2]}` : event[1] === "hold" ? "存分" : String(event[1]);
        }
      } else if (event && typeof event === "object") {
        actor = event.guess ? "你" : (event.action || "进展");
        action = event.guess ? `${event.guess}${event.correct ? " · 命中" : " · 未命中"}`
          : (event.question || event.answer || event.action || "进展");
      } else if (typeof event === "string") {
        action = event;
      }
      const item = node("li");
      if (game.game_type === "gomoku") {
        item.appendChild(node("small", "history-step", String(events.length - index)));
        item.classList.add("gomoku-history-item");
      }
      item.append(node("span", "", actor), node("span", "", action));
      list.appendChild(item);
    });
    if (!events.length) list.append(node("li", "", "等待第一步"));
  }

  function render({force = true} = {}) {
    if (!game) return;
    const signature = JSON.stringify([game, busy, selected, game.game_type === "gomoku" ? null : selectedPiece]);
    if (!force && signature === renderedSignature) return;
    renderedSignature = signature;
    const focusKey = document.activeElement?.dataset?.focusKey;
    const label = labels[game.game_type] || "V2 原生对局";
    $("gameTitle").textContent = label;
    $("gameCode").textContent = game.game_type === "gomoku" ? "15 × 15 · 黑棋先行 · 无禁手" : "一起玩 · 游戏房间";
    $("roundState").textContent = stateLabel[game.status] || game.status;
    if (game.game_type === "gomoku") {
      gomoku.renderToolbar(game.state || {});
      $("roundState").textContent = game.status === "active" ? gomoku.phase() : (stateLabel[game.status] || game.status);
    } else { $("boardToolbar").hidden = true; }
    renderBoard(game.state || {});
    renderPieceTray(game.state || {});
    renderControls(game.state || {});
    renderHistory();
    if (focusKey) document.querySelector?.(`[data-focus-key="${focusKey}"]`)?.focus({preventScroll: true});
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {cache: "no-store", ...options});
    const result = await response.json();
    if (!response.ok || result?.status === "error") throw new Error(result?.message || "请求失败");
    return result.data ?? result;
  }

  const errors = {
    game_illegal_move: "这一步未落下，棋盘已同步，请重新选择空位",
    game_target_occupied: "这个交叉点已有棋子，请选择空位",
    game_web_link_expired: "对局链接已失效，请在聊天中重新打开房间",
    game_not_found: "这局已不可用，请在聊天中打开当前房间",
    game_not_active: "本局已结束，棋盘已同步",
    game_not_found_in_scope: "这局已不可用，请在聊天中打开当前房间",
    invalid_game_arguments: "落子信息未被接受，请同步棋盘后重新选择",
  };
  const errorMessage = (error, fallback) => errors[error.message]
    || (/[\u3400-\u9fff]/.test(error.message || "") ? error.message : fallback);

  async function load({quiet = true, recovery = false} = {}) {
    if (loading || dragState || gomoku.isInteracting() || (busy && !recovery)) return;
    loading = true;
    const sequence = ++requestSequence;
    try {
      const result = await fetchJSON(`/api/native/${encodeURIComponent(token)}/state`);
      if (sequence !== requestSequence || dragState || gomoku.isInteracting()) return;
      game = result.game;
      $("connectionBadge").dataset.state = "online";
      $("connectionBadge").querySelector("span").textContent = "实时同步";
      render({force: false});
      if (!quiet) setNotice("");
    } catch (error) {
      if (sequence !== requestSequence) return;
      if (!quiet || !game) setNotice(errorMessage(error, "对局暂时无法读取"), true);
      $("connectionBadge").dataset.state = "error";
      $("connectionBadge").querySelector("span").textContent = "连接中断";
    } finally {
      loading = false;
    }
  }

  async function sendAction(payload) {
    if (busy || !token) return;
    gomoku.clearPending();
    if (payload?.action === "interact") selectedPiece = null;
    busy = true;
    requestSequence += 1;
    render();
    try {
      const result = await fetchJSON(`/api/native/${encodeURIComponent(token)}/action`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      game = result.game;
      setNotice("");
    } catch (error) {
      setNotice(errorMessage(error, "这一步未收到确认，请以同步后的棋盘为准"), true);
      await load({quiet: true, recovery: true});
    } finally {
      busy = false;
      render();
    }
  }

  if (!token) {
    setNotice("对局链接无效", true);
  } else {
    load({quiet: false});
    timer = window.setInterval(() => load(), 1800);
  }
  window.addEventListener("pagehide", () => window.clearInterval(timer));
})();
