(() => {
  "use strict";

  // One coordinate system for lines, hit areas, stones and drag destinations.
  const SIZE = 15;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const colorName = (color) => color === 1 ? "黑棋" : "白棋";
  const coordinate = (row, column) => `${String.fromCharCode(65 + column)}${row + 1}`;
  const percent = (index) => `${((index + .5) / SIZE) * 100}%`;

  function winningChain(board, winner, lastMove) {
    if (!winner) return [];
    const chains = [];
    for (let row = 0; row < SIZE; row += 1) {
      for (let column = 0; column < SIZE; column += 1) {
        if (board[row]?.[column] !== winner) continue;
        for (const [dr, dc] of [[0, 1], [1, 0], [1, 1], [1, -1]]) {
          if (board[row - dr]?.[column - dc] === winner) continue;
          const chain = [];
          let r = row;
          let c = column;
          while (r >= 0 && r < SIZE && c >= 0 && c < SIZE && board[r]?.[c] === winner) {
            chain.push([r, c]); r += dr; c += dc;
          }
          if (chain.length >= 5) chains.push(chain);
        }
      }
    }
    return chains.find(chain => chain.some(([r, c]) => r === lastMove?.[0] && c === lastMove?.[1]))
      || chains[0] || [];
  }

  window.CompanionGomokuRoom = {
    create({node, $, getGame, isBusy, getSelectedPiece, clearSelectedPiece,
      setSelectedPiece, sendAction, render, setNotice, refreshControls}) {
      let freePlacement = false;
      const touchLayout = window.matchMedia?.("(pointer: coarse), (max-width: 560px)").matches ?? false;
      let confirmPlacement = touchLayout;
      let showNumbers = false;
      let pending = null;
      let submission = null;
      let hover = null;
      let view = null;
      let previousPieces = null;
      let focusPoint = [7, 7];
      let currentGameId = null;

      const humanTurn = (state) => state.turn === state.human_color;
      const active = () => getGame()?.status === "active" && !isBusy();
      const sourceForPoint = () => freePlacement ? getSelectedPiece()
        : {kind: "move", color: getGame().state.human_color};
      const input = window.CompanionGomokuInput.create({node, getSurface: () => view?.surface,
        getSource: sourceForPoint, canInteract: () => active() && (freePlacement || humanTurn(getGame().state)),
        onSelect: selectPiece, onPreview: preview, onDrop: drop,
        onCancel: reason => { cancelSelection(); setNotice(reason === "outside" ? "已取消拖动，棋子放回原处" : "已放回棋子"); },
        onLift: (source, lifted) => view?.pieces.get(source.piece_id)?.classList.toggle("piece-lifted", lifted),
      });

      function boardPieces(state) {
        const moves = getGame().moves || [];
        return moves.length ? moves.map(([row, column, color], index) => ({row, column, color, piece_id: `piece-${index + 1}`}))
          : (state.pieces || []);
      }

      function sameSource(a, b) {
        return a?.kind === b?.kind && (a?.kind === "tray" ? a.color === b.color : a?.piece_id === b?.piece_id);
      }

      function origin(source) {
        return source?.kind === "board" ? boardPieces(getGame().state).find(piece => piece.piece_id === source.piece_id) : null;
      }

      function atOrigin(target, source) {
        const start = origin(source);
        return start && target.row === start.row && target.column === start.column;
      }

      function refreshSelection() {
        if (!view) return;
        const held = getSelectedPiece();
        view.pieces.forEach((element, pieceId) => {
          const selected = held?.kind === "board" && held.piece_id === pieceId;
          element.classList.toggle("selected", selected);
          element.setAttribute("aria-pressed", String(selected));
        });
        view.tray.forEach(([element, source]) => element.setAttribute("aria-pressed", String(sameSource(held, source))));
        if (view.trayHint) view.trayHint.textContent = held ? `已拿起${colorName(held.color)} · 点空位落下，再点棋子放回` : "点击取子，也可以直接拖到棋盘";
        view.surface.dataset.holding = String(Boolean(held));
        refreshControls();
        preview(hover?.target || null, hover?.meta);
      }

      function selectPiece(source) {
        if (!active() || !freePlacement) return;
        const putBack = sameSource(getSelectedPiece(), source);
        setSelectedPiece(putBack ? null : source);
        hover = null;
        setNotice(putBack ? "已放回棋子" : `已拿起${colorName(source.color)}，点空位落下，再点一次放回`);
        refreshSelection();
      }

      function cancelSelection() {
        input.cancel();
        clearSelectedPiece(); pending = null; hover = null;
        refreshSelection();
      }

      function drop(target, interaction, source) {
        if (!active()) return;
        focusPoint = [target.row, target.column];
        if (freePlacement && !source) { setNotice("从棋盒取一子，或拿起棋盘上的棋子"); return; }
        if (atOrigin(target, source)) { cancelSelection(); setNotice("已放回棋子"); return; }
        if (getGame().state.board[target.row]?.[target.column]) {
          preview(target, {source});
          setNotice("这个交叉点已有棋子，换一个空位即可"); return;
        }
        hover = null;
        if (!freePlacement && confirmPlacement) {
          pending = target;
          setNotice(""); refreshSelection(); return;
        }
        submission = {target, source};
        clearSelectedPiece();
        sendAction(freePlacement ? {action: "interact", source, target, interaction} : {action: "move", ...target});
      }

      function drawLens(target, source, invalid) {
        const key = `${target.row}:${target.column}:${source.color}:${invalid}`;
        if (view.lensKey === key) return;
        view.lensKey = key;
        view.lens.replaceChildren(node("strong", "gomoku-lens-label", `${coordinate(target.row, target.column)} · ${invalid ? "已有棋子" : "放大落点"}`));
        const grid = node("div", "gomoku-lens-grid");
        for (let dr = -2; dr <= 2; dr += 1) {
          for (let dc = -2; dc <= 2; dc += 1) {
            const row = target.row + dr, column = target.column + dc;
            const cell = node("span", "gomoku-lens-cell");
            if (row < 0 || column < 0 || row >= SIZE || column >= SIZE) cell.classList.add("outside");
            else {
              const center = dr === 0 && dc === 0;
              const color = getGame().state.board[row]?.[column] || (center ? source.color : 0);
              if (color) cell.appendChild(node("span", `stone ${color === 1 ? "stone-black" : "stone-white"}`));
              if (center) { cell.classList.add("lens-target"); if (invalid) cell.classList.add("invalid"); }
            }
            grid.appendChild(cell);
          }
        }
        view.lens.appendChild(grid);
      }

      function preview(target, meta = {}) {
        if (!view) return;
        hover = target ? {target, meta} : null;
        const chosen = submission?.target || target || pending;
        const source = submission?.source || meta.source || sourceForPoint();
        const invalid = Boolean(chosen && getGame().state.board[chosen.row]?.[chosen.column] && !atOrigin(chosen, source));
        view.target.hidden = !chosen || !source;
        view.lens.hidden = !chosen || !source || !(meta.touch || (pending && touchLayout));
        view.target.classList.toggle("invalid", invalid);
        view.target.classList.toggle("sending", Boolean(submission));
        view.surface.classList.toggle("preview-active", Boolean(chosen && source));
        if (chosen && source) {
          view.target.style.left = percent(chosen.column);
          view.target.style.top = percent(chosen.row);
          view.targetStone.className = `stone ${source.color === 1 ? "stone-black" : "stone-white"}`;
          view.readout.textContent = `${colorName(source.color)} · ${coordinate(chosen.row, chosen.column)}${invalid ? " · 已有棋子" : submission ? " · 正在同步" : pending ? " · 确认后落下" : " · 松手或点击落下"}`;
          if (!view.lens.hidden) {
            view.lens.dataset.side = chosen.column < 7 ? "right" : "left";
            drawLens(chosen, source, invalid);
          }
        } else view.readout.textContent = getGame().status !== "active" ? "本局棋盘已保留"
          : freePlacement ? "拿起棋子后选择空位 · 拖出棋盘放回"
          : confirmPlacement ? "点选或按住滑动选点 · 确认后落子" : "点击落子，也可按住滑动调整落点";
      }

      window.addEventListener("keydown", event => {
        if (event.key !== "Escape" || getGame()?.game_type !== "gomoku" || isBusy()) return;
        if (pending || getSelectedPiece() || input.isActive()) {
          event.preventDefault(); cancelSelection(); setNotice("已取消选择");
        }
      });

      function button(label, callback, className = "") {
        const element = node("button", `control-button ${className}`.trim(), label);
        element.type = "button";
        element.addEventListener("click", callback);
        return element;
      }

      function toggle(label, pressed, callback, key) {
        const element = button(label, callback, "gomoku-option");
        element.setAttribute("aria-pressed", String(pressed));
        element.dataset.focusKey = key;
        element.disabled = isBusy();
        return element;
      }

      function phase() {
        const game = getGame();
        if (game.status === "finished") return {player: "你赢了", bot: "陪伴者赢了", draw: "本局平局"}[game.outcome] || "本局结束";
        if (game.status !== "active") return "对局已关闭";
        if (isBusy()) return "正在同步落子…";
        if (freePlacement) return "自由摆子";
        return humanTurn(game.state) ? `轮到你 · ${colorName(game.state.human_color)}` : `轮到陪伴者 · ${colorName(game.state.bot_color)}`;
      }

      function synchronize(state) {
        const game = getGame();
        if (game.game_id !== currentGameId) {
          currentGameId = game.game_id;
          pending = null;
          submission = null;
          hover = null;
          previousPieces = null;
          clearSelectedPiece();
          freePlacement = false;
          focusPoint = [7, 7];
        }
        if (game.status !== "active") {
          freePlacement = false;
          clearSelectedPiece();
        }
        if (!isBusy()) submission = null;
        if (getSelectedPiece()?.kind === "board" && !origin(getSelectedPiece())) clearSelectedPiece();
        if (game.status !== "active" || !humanTurn(state)
            || (pending && state.board?.[pending.row]?.[pending.column])) pending = null;
      }

      function renderToolbar(state) {
        const host = $("boardToolbar");
        host.hidden = false;
        host.replaceChildren();
        synchronize(state);
        const status = node("div", "gomoku-status");
        const markerColor = getGame().status === "finished" ? (state.winner || state.human_color) : (state.turn || state.human_color);
        const marker = node("span", `turn-stone ${markerColor === 1 ? "black" : "white"}`);
        marker.setAttribute("aria-hidden", "true");
        const text = node("div");
        text.append(node("strong", "", phase()), node("p", "summary-line", getGame().status === "active"
          ? (freePlacement ? "点击或拖动取子 · 再点一次放回 · Esc 取消" : "点击或滑动选落点 · 先连成五子获胜")
          : (getGame().status === "finished"
            ? (getGame().outcome === "draw" ? "本局平局，棋盘已保留" : "最后一手与获胜连线已标出") : "棋盘保留本局记录")));
        status.append(marker, text);
        const options = node("div", "gomoku-options");
        options.append(toggle("显示手数", showNumbers, () => { showNumbers = !showNumbers; render(); }, "gomoku-numbers"));
        if (getGame().status === "active") {
          if (!freePlacement) options.append(toggle("落子确认", confirmPlacement, () => {
            cancelSelection(); confirmPlacement = !confirmPlacement; render();
          }, "gomoku-confirm-mode"));
          options.append(toggle(freePlacement ? "返回对弈" : "自由摆子", freePlacement, () => {
            cancelSelection(); freePlacement = !freePlacement; setNotice(""); render();
          }, "gomoku-free-mode"));
        }
        host.append(status, options);
      }

      function svgElement(tag, attributes) {
        const element = document.createElementNS(SVG_NS, tag);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
      }

      function renderBoard(state) {
        const stage = node("div", "board-stage gomoku-stage");
        stage.style.setProperty("--board-size", SIZE);
        stage.dataset.mode = freePlacement ? "free" : "play";
        const surface = node("div", "gomoku-intersections");
        surface.dataset.interactive = String(active() && (freePlacement || humanTurn(state)));
        view = {surface, pieces: new Map(), tray: [], lensKey: null};
        input.bindSurface(surface);
        const currentPieces = boardPieces(state);
        const lines = svgElement("svg", {viewBox: "0 0 450 450", "aria-hidden": "true", class: "gomoku-lines"});
        const path = Array.from({length: SIZE}, (_, index) => {
          const position = 15 + index * 30;
          return `M15 ${position}H435M${position} 15V435`;
        }).join("");
        lines.appendChild(svgElement("path", {d: path}));
        [[3, 3], [3, 11], [7, 7], [11, 3], [11, 11]].forEach(([row, column]) => {
          lines.appendChild(svgElement("circle", {cx: 15 + column * 30, cy: 15 + row * 30, r: 2.6}));
        });
        surface.appendChild(lines);
        const axes = node("div", "gomoku-axes");
        axes.setAttribute("aria-hidden", "true");
        for (let index = 0; index < SIZE; index += 1) {
          const column = node("span", "axis-column", String.fromCharCode(65 + index));
          column.style.left = percent(index);
          const row = node("span", "axis-row", String(index + 1));
          row.style.top = percent(index);
          axes.append(column, row);
        }
        surface.appendChild(axes);
        const grid = node("div", "gomoku-hit-grid");
        grid.setAttribute("role", "group");
        grid.setAttribute("aria-label", "15 行 15 列五子棋棋盘，方向键选择交叉点，回车落子");
        const points = [];
        state.board.forEach((row, rowIndex) => row.forEach((color, columnIndex) => {
          const point = node("button", "gomoku-point");
          point.type = "button";
          point.dataset.focusKey = `point-${rowIndex}-${columnIndex}`;
          point.dataset.row = rowIndex;
          point.dataset.column = columnIndex;
          point.setAttribute("aria-label", `第 ${rowIndex + 1} 行，第 ${columnIndex + 1} 列${color ? `，${colorName(color)}${freePlacement ? "，可拿起或拖动" : ""}` : ""}`);
          const enabled = active() && (freePlacement || humanTurn(state));
          point.disabled = !enabled;
          point.setAttribute("aria-disabled", String(!enabled || (Boolean(color) && !freePlacement)));
          point.tabIndex = rowIndex === focusPoint[0] && columnIndex === focusPoint[1] ? 0 : -1;
          if (color) point.classList.add("occupied");
          const target = {row: rowIndex, column: columnIndex, x: .5, y: .5};
          const piece = color && currentPieces.find(item => item.row === rowIndex && item.column === columnIndex);
          if (freePlacement && piece) input.bindSource(point, {kind: "board", piece_id: piece.piece_id, color});
          else if (!color) input.bindPoint(point, target);
          point.addEventListener("focus", () => {
            focusPoint = [rowIndex, columnIndex];
            if (enabled) preview(target, {source: sourceForPoint()});
          });
          point.addEventListener("keydown", (event) => {
            if (event.key === "Escape") { cancelSelection(); return; }
            const offset = {ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1]}[event.key];
            if (!offset) return;
            event.preventDefault();
            const r = Math.max(0, Math.min(SIZE - 1, rowIndex + offset[0]));
            const c = Math.max(0, Math.min(SIZE - 1, columnIndex + offset[1]));
            point.tabIndex = -1;
            focusPoint = [r, c];
            const next = points[r * SIZE + c];
            next.tabIndex = 0; next.focus();
          });
          points.push(point); grid.appendChild(point);
        }));
        surface.appendChild(grid);
        const layer = node("div", "piece-layer gomoku-pieces");
        const moves = getGame().moves || [];
        const last = state.last_move || moves.at(-1)?.slice(0, 2);
        const chain = getGame().status === "finished" ? winningChain(state.board, state.winner, last) : [];
        if (chain.length) {
          const [start, end] = [chain[0], chain.at(-1)];
          const line = svgElement("svg", {viewBox: "0 0 450 450", class: "gomoku-winning-line", "aria-hidden": "true"});
          line.appendChild(svgElement("line", {x1: 15 + start[1] * 30, y1: 15 + start[0] * 30,
            x2: 15 + end[1] * 30, y2: 15 + end[0] * 30}));
          layer.appendChild(line);
        }
        // Logical cells are authoritative; old in-cell offsets must not scatter stones.
        currentPieces.forEach((piece, index) => {
          const element = node("button", "floating-piece gomoku-piece");
          const lastMove = piece.row === last?.[0] && piece.column === last?.[1];
          const winning = chain.some(([r, c]) => piece.row === r && piece.column === c);
          const owner = piece.color === state.human_color ? "你" : "陪伴者";
          element.type = "button";
          element.dataset.pieceId = piece.piece_id;
          element.dataset.focusKey = piece.piece_id;
          element.tabIndex = freePlacement && active() ? 0 : -1;
          element.disabled = !active() || !freePlacement;
          element.setAttribute("aria-label", `${owner}的${colorName(piece.color)} ${coordinate(piece.row, piece.column)}，第 ${index + 1} 手${lastMove ? "，最后一手" : ""}${winning ? "，获胜连线" : ""}${freePlacement ? "，可拿起或拖动" : ""}`);
          element.style.left = percent(piece.column);
          element.style.top = percent(piece.row);
          view.pieces.set(piece.piece_id, element);
          const stone = node("span", `stone ${piece.color === 1 ? "stone-black" : "stone-white"}`);
          element.appendChild(stone);
          if (lastMove) element.classList.add("last-move");
          if (winning) element.classList.add("winning-piece");
          if (showNumbers) { stone.textContent = String(index + 1); element.classList.add("numbered"); }
          const held = getSelectedPiece()?.piece_id === piece.piece_id;
          if (held) element.classList.add("selected");
          if (freePlacement) element.setAttribute("aria-pressed", String(held));
          const previous = previousPieces?.get(piece.piece_id);
          if (previousPieces && !isBusy() && (!previous || previous.row !== piece.row || previous.column !== piece.column)) element.classList.add("just-placed");
          if (submission?.source.piece_id === piece.piece_id) element.classList.add("piece-lifted");
          const source = {kind: "board", piece_id: piece.piece_id, color: piece.color};
          if (freePlacement) input.bindSource(element, source);
          layer.appendChild(element);
        });
        surface.appendChild(layer);
        previousPieces = new Map(currentPieces.map(piece => [piece.piece_id, piece]));
        view.target = node("div", "gomoku-target");
        view.target.setAttribute("aria-hidden", "true");
        view.targetStone = node("span", "stone");
        view.target.appendChild(view.targetStone);
        view.lens = node("div", "gomoku-lens");
        view.lens.setAttribute("aria-hidden", "true");
        surface.append(view.target, view.lens);
        view.readout = node("p", "gomoku-interaction-readout");
        stage.appendChild(surface);
        $("gameBoard").append(stage, view.readout);
        preview(null);
      }

      function renderTray(state) {
        const tray = $("pieceTray");
        tray.replaceChildren();
        tray.hidden = !freePlacement || getGame().status !== "active";
        if (tray.hidden) return;
        tray.appendChild(node("span", "piece-tray-heading", "棋盒"));
        [state.human_color, state.bot_color].forEach(color => {
          const source = {kind: "tray", color};
          const piece = node("button", "control-button gomoku-tray-piece");
          piece.type = "button";
          piece.append(node("span", `stone ${color === 1 ? "stone-black" : "stone-white"}`),
            node("span", "", `${colorName(color)} · ${color === state.human_color ? "你" : "陪伴者"}`));
          piece.setAttribute("aria-label", `${colorName(color)} · ${color === state.human_color ? "你" : "陪伴者"}，点击取子或拖到棋盘`);
          piece.disabled = !active();
          piece.dataset.focusKey = `tray-${color}`;
          piece.setAttribute("aria-pressed", String(getSelectedPiece()?.kind === "tray" && getSelectedPiece().color === color));
          input.bindSource(piece, source);
          view.tray.push([piece, source]);
          tray.appendChild(piece);
        });
        view.trayHint = node("span", "piece-tray-hint", getSelectedPiece() ? "已拿起棋子 · 点空位落下，再点棋子放回" : "点击取子，也可以直接拖到棋盘");
        tray.appendChild(view.trayHint);
      }

      function renderControls(controls, state) {
        if (freePlacement) {
          const cancel = button("放回棋子", () => { cancelSelection(); setNotice("已放回棋子"); });
          cancel.disabled = !getSelectedPiece() || isBusy();
          controls.appendChild(cancel);
        } else if (!humanTurn(state)) {
          const reply = button("让陪伴者接着下", () => sendAction({action: "reply"}), "primary");
          reply.disabled = isBusy();
          controls.appendChild(reply);
        } else if (confirmPlacement) {
          controls.appendChild(node("span", "gomoku-pending-label", pending ? `落点 ${coordinate(pending.row, pending.column)}` : "先选择一个交叉点"));
          const confirm = button("确认落子", () => {
            if (!pending || !active()) return;
            const target = pending; pending = null;
            submission = {target, source: sourceForPoint()};
            sendAction({action: "move", ...target});
          }, "primary");
          confirm.dataset.focusKey = "gomoku-place";
          confirm.disabled = !pending || !active();
          const cancel = button("取消", () => { cancelSelection(); setNotice(""); });
          cancel.disabled = !pending || isBusy();
          controls.append(confirm, cancel);
        } else controls.appendChild(node("span", "summary-line", "棋子上的小圆点标记最后一手"));
      }

      return {phase, renderToolbar, renderBoard, renderTray, renderControls,
        clearPending() { pending = null; hover = null; }, isFreePlacement() { return freePlacement; },
        isInteracting: input.isActive};
    },
  };
})();
