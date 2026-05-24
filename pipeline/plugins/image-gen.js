import { tool } from "@opencode-ai/plugin";
import OpenAI from "openai";
import fs from "fs";
import path from "path";

function loadApiKey(worktree) {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY;
  // Fallback: read from .env at project root
  try {
    const envPath = path.join(worktree, ".env");
    const content = fs.readFileSync(envPath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("OPENAI_API_KEY=")) {
        return trimmed.split("=", 2)[1].trim().replace(/^["']|["']$/g, "");
      }
    }
  } catch {}
  return undefined;
}

export const ImageGenPlugin = async (ctx) => {
  return {
    tool: {
      generate_image: tool({
        description:
          "Generate an image using AI (GPT image-2) and save it to the site/assets/ folder. " +
          "Use this to create images for the website based on the specification. " +
          "Returns the relative path to the saved image (e.g., assets/hero-bg.png) which you can use in HTML src attributes.",
        args: {
          prompt: tool.schema
            .string()
            .describe(
              "Detailed description of the image to generate. Be specific about subject, style, colors, mood, and composition."
            ),
          filename: tool.schema
            .string()
            .describe(
              'Filename for the image (without directory path), e.g. "hero-bg.png", "team-photo.png". Must end in .png'
            ),
          size: tool.schema
            .enum(["1024x1024", "1024x1536", "1536x1024"])
            .describe(
              "Image dimensions. Use 1536x1024 for landscape/hero images, 1024x1536 for portrait, 1024x1024 for square."
            )
            .default("1536x1024"),
        },
        async execute(args, context) {
          const assetsDir = path.join(context.directory, "site", "assets");
          fs.mkdirSync(assetsDir, { recursive: true });

          const outputPath = path.join(assetsDir, args.filename);
          const relativePath = `assets/${args.filename}`;

          const apiKey = loadApiKey(context.worktree);
          const openai = new OpenAI(apiKey ? { apiKey } : undefined);

          try {
            const result = await openai.images.generate({
              model: "gpt-image-2",
              prompt: args.prompt,
              n: 1,
              size: args.size,
            });

            const imageBase64 = result.data[0].b64_json;
            if (!imageBase64) {
              return `Error: No image data returned from API`;
            }

            const imageBytes = Buffer.from(imageBase64, "base64");
            fs.writeFileSync(outputPath, imageBytes);

            return `Image saved to ${relativePath} (${imageBytes.length} bytes). Use this path in your HTML: <img src="${relativePath}" alt="...">`;
          } catch (err) {
            return `Error generating image: ${err.message}`;
          }
        },
      }),
    },
  };
};
