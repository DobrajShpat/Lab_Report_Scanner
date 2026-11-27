const cache = new Map<string, Promise<HTMLImageElement>>();

export function loadSharedImage(url: string): Promise<HTMLImageElement> {
  if (!cache.has(url)) {
    cache.set(
      url,
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
        img.src = url;
      }),
    );
  }
  return cache.get(url)!;
}

export function clearImageCache() {
  cache.clear();
}
