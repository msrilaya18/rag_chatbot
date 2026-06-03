import "./globals.css";

export const metadata = {
  title: "RAG Social Video Comparison Chatbot",
  description: "Analyze and compare YouTube videos and Instagram Reels side-by-side using LangGraph RAG",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
