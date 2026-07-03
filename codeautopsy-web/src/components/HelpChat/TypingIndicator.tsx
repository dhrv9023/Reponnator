import React from "react";

export const TypingIndicator: React.FC = () => {
  return (
    <div className="flex items-start gap-2.5 mb-2.5 animate-message-fade">
      {/* Bot Icon */}
      <div className="w-8 h-8 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-sm shadow-sm flex-shrink-0">
        🤖
      </div>
      
      {/* Bubble Shell */}
      <div className="bg-white border border-gray-100 text-gray-800 text-sm rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm max-w-[80%] flex items-center gap-1.5 h-[38px]">
        <span 
          className="w-2.5 h-2.5 bg-indigo-400 rounded-full animate-bounce-dot"
          style={{ animationDelay: "0ms" }}
        />
        <span 
          className="w-2.5 h-2.5 bg-indigo-400 rounded-full animate-bounce-dot"
          style={{ animationDelay: "150ms" }}
        />
        <span 
          className="w-2.5 h-2.5 bg-indigo-400 rounded-full animate-bounce-dot"
          style={{ animationDelay: "300ms" }}
        />
      </div>
    </div>
  );
};

export default TypingIndicator;
