import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function GlobalTooltip() {
  const [targetInfo, setTargetInfo] = useState(null);
  const [style, setStyle] = useState({ opacity: 0 });
  const [arrowStyle, setArrowStyle] = useState({});
  const [activeSide, setActiveSide] = useState("top");
  const tooltipRef = useRef(null);

  useEffect(() => {
    let currentEl = null;

    const onMouseOver = (e) => {
      // Find closest element with data-tooltip
      const el = e.target.closest("[data-tooltip]");
      if (!el) return;
      currentEl = el;
      const text = el.getAttribute("data-tooltip");
      if (!text || !text.trim()) return;
      const prefPos = el.getAttribute("data-tooltip-pos") || "top";
      const rect = el.getBoundingClientRect();

      setTargetInfo({
        text,
        prefPos,
        rect: {
          top: rect.top,
          bottom: rect.bottom,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          height: rect.height,
        },
      });
    };

    const onMouseOut = (e) => {
      if (!currentEl) return;
      const related = e.relatedTarget;
      if (currentEl.contains(related)) return;
      currentEl = null;
      setTargetInfo(null);
    };

    const onScroll = () => {
      currentEl = null;
      setTargetInfo(null);
    };

    const onMouseDown = () => {
      currentEl = null;
      setTargetInfo(null);
    };

    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("mouseover", onMouseOver, true);
    document.addEventListener("mouseout", onMouseOut, true);
    window.addEventListener("scroll", onScroll, true);

    return () => {
      document.removeEventListener("mousedown", onMouseDown, true);
      document.removeEventListener("mouseover", onMouseOver, true);
      document.removeEventListener("mouseout", onMouseOut, true);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, []);

  useLayoutEffect(() => {
    if (!targetInfo || !tooltipRef.current) return;

    const tt = tooltipRef.current;
    const ttW = tt.offsetWidth || 240;
    const ttH = tt.offsetHeight || 44;
    const { rect, prefPos } = targetInfo;
    const vpW = window.innerWidth;
    const vpH = window.innerHeight;
    const pad = 12;

    const targetCenterX = rect.left + rect.width / 2;
    const targetCenterY = rect.top + rect.height / 2;

    let side = prefPos;
    let top = 0;
    let left = 0;

    // Automatic flip if not enough space on requested side
    if (side === "top" && rect.top - ttH - 10 < pad) {
      side = "bottom";
    } else if (side === "bottom" && rect.bottom + ttH + 10 > vpH - pad) {
      side = "top";
    } else if (side === "left" && rect.left - ttW - 10 < pad) {
      side = "right";
    } else if (side === "right" && rect.right + ttW + 10 > vpW - pad) {
      side = "left";
    }

    if (side === "top" || side === "bottom") {
      top = side === "top" ? rect.top - ttH - 8 : rect.bottom + 8;
      left = targetCenterX - ttW / 2;
      // Clamp horizontally strictly inside viewport
      left = Math.max(pad, Math.min(vpW - ttW - pad, left));

      // Arrow position pointing to target button's center
      const arrowX = targetCenterX - left;
      setArrowStyle({
        left: `${Math.max(12, Math.min(ttW - 16, arrowX))}px`,
        transform: "translateX(-50%)",
      });
    } else {
      // left or right
      left = side === "left" ? rect.left - ttW - 8 : rect.right + 8;
      top = targetCenterY - ttH / 2;
      // Clamp vertically strictly inside viewport
      top = Math.max(pad, Math.min(vpH - ttH - pad, top));

      // Arrow position pointing to target button's center
      const arrowY = targetCenterY - top;
      setArrowStyle({
        top: `${Math.max(10, Math.min(ttH - 14, arrowY))}px`,
        transform: "translateY(-50%)",
      });
    }

    setActiveSide(side);
    setStyle({
      top: `${Math.round(top)}px`,
      left: `${Math.round(left)}px`,
      opacity: 1,
    });
  }, [targetInfo]);

  if (!targetInfo) return null;

  return createPortal(
    <div
      ref={tooltipRef}
      className="floating-tooltip"
      data-side={activeSide}
      style={style}
      role="tooltip"
      aria-hidden="true"
    >
      {targetInfo.text}
      <span className="floating-tooltip-arrow" style={arrowStyle} />
    </div>,
    document.body
  );
}
