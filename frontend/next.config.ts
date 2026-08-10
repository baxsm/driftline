import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the floating dev badge sits over the viewer's reset control and leaks into screenshots
  devIndicators: false,
};

export default nextConfig;
