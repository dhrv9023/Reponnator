import React from "react";
import { ChatMessage } from "./useChat";

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const { type, text, timestamp } = message;
  const isBot = type === "bot";

  const formatTime = (date: Date) => {
    try {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  // Render newlines as <br />
  const renderedText = text.split("\n").map((line, index, arr) => (
    <React.Fragment key={index}>
      {line}
      {index < arr.length - 1 && <br />}
    </React.Fragment>
  ));

  if (isBot) {
    return (
      <div className="flex items-start gap-2.5 mb-3.5 animate-message-fade max-w-[85%] self-start">
        {/* Bot Avatar */}
        <div className="w-8 h-8 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-sm shadow-sm flex-shrink-0 select-none">
          🤖
        </div>

        {/* Message Content */}
        <div className="flex flex-col gap-1">
          <div className="bg-white border border-gray-100 text-gray-800 text-sm rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm leading-relaxed break-words max-w-full">
            {renderedText}
          </div>
          {/* Timestamp */}
          <span className="text-[10px] text-gray-400 pl-1">
            {formatTime(timestamp)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1 items-end mb-3.5 animate-message-fade max-w-[85%] self-end">
      {/* Message Content */}
      <div className="bg-indigo-600 text-white text-sm rounded-2xl rounded-tr-sm px-4 py-3 shadow-md leading-relaxed break-words max-w-full">
        {renderedText}
      </div>
      {/* Timestamp */}
      <span className="text-[10px] text-gray-400 pr-1">
        {formatTime(timestamp)}
      </span>
    </div>
  );
};

export default MessageBubble;
