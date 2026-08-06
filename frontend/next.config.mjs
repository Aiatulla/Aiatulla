/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle with only the modules actually used, so
  // the runtime image needs no node_modules at all.
  output: "standalone",
};

export default nextConfig;
