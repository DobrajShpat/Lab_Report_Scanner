import { memo, useEffect, useRef } from 'react';
import { loadSharedImage } from '../shared/imageCache';

export type OcrBBoxLine = {
  text: string;
  confidence: number;
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
};

type Props = {
  imageUrl: string;
  line: OcrBBoxLine;
  size?: number;
  alt: string;
};

export const OcrLineThumbnail = memo(function OcrLineThumbnail({
  imageUrl,
  line,
  size = 56,
  alt,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let active = true;
    const canvas = canvasRef.current;
    if (!canvas) return;

    loadSharedImage(imageUrl)
      .then((img) => {
        if (!active) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const pad = 4;
        const sx = Math.max(0, line.x_min - pad);
        const sy = Math.max(0, line.y_min - pad);
        const sw = Math.max(1, line.x_max - line.x_min + pad * 2);
        const sh = Math.max(1, line.y_max - line.y_min + pad * 2);

        ctx.clearRect(0, 0, size, size);
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, size, size);

        const scale = Math.min(size / sw, size / sh);
        const dw = sw * scale;
        const dh = sh * scale;
        const dx = (size - dw) / 2;
        const dy = (size - dh) / 2;

        ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
        ctx.strokeStyle = '#0f766e';
        ctx.lineWidth = 1;
        ctx.strokeRect(dx, dy, dw, dh);
      })
      .catch(() => {
        if (!active || !canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.fillStyle = '#f1f5f9';
        ctx.fillRect(0, 0, size, size);
      });

    return () => {
      active = false;
    };
  }, [imageUrl, line.x_min, line.y_min, line.x_max, line.y_max, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      role="img"
      aria-label={alt}
      className="shrink-0 rounded-lg border border-slate-200 bg-slate-50"
    />
  );
});
