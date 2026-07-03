import React, { useState, useEffect } from "react";
import { useChat } from "./useChat";
import ChatWidget from "./ChatWidget";
import "./helpChat.css";

export const HelpChat: React.FC = () => {
  const chat = useChat();
  const { isOpen, openChat, closeChat } = chat;

  const [showBadge, setShowBadge] = useState<boolean>(true);
  const [shouldPulse, setShouldPulse] = useState<boolean>(true);

  // Unread badge fades after 5s, FAB attention pulse stops after 3s
  useEffect(() => {
    const badgeTimer = setTimeout(() => setShowBadge(false), 5000);
    const pulseTimer = setTimeout(() => setShouldPulse(false), 3000);

    return () => {
      clearTimeout(badgeTimer);
      clearTimeout(pulseTimer);
    };
  }, []);

  const handleFABClick = () => {
    if (isOpen) {
      closeChat();
    } else {
      openChat();
      setShowBadge(false); // Clear badge once clicked
    }
  };

  return (
    <div className="help-chat-widget-root select-none">
      {/* 
        Chat Widget Container
        Using state-driven opacity, scale, and pointer-events classes
        for premium browser-native entry and exit slide-and-fade transitions.
      */}
      <div
        className={`fixed bottom-24 right-4 z-50 w-[calc(100vw-2rem)] sm:w-[380px] h-[calc(100vh-7.5rem)] sm:h-[560px] transition-all duration-300 origin-bottom-right transform ${
          isOpen
            ? "opacity-100 scale-100 translate-y-0"
            : "opacity-0 scale-95 translate-y-8 pointer-events-none"
        }`}
      >
        <ChatWidget
          chat={chat}
          onClose={closeChat}
          onMinimize={closeChat}
        />
      </div>

      {/* Floating Action Button (FAB) */}
      <button
        onClick={handleFABClick}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 active:scale-95 text-white flex items-center justify-center shadow-xl select-none cursor-pointer focus:outline-none transition-all duration-200 ${
          shouldPulse ? "animate-fab-attention" : "box-shadow: 0 8px 32px rgba(99, 102, 241, 0.4)"
        }`}
        aria-label="Help Chat"
      >
        {/* Toggle Icons */}
        {isOpen ? (
          <svg
            className="w-6 h-6 transition-all duration-300 transform rotate-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2.5"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        ) : (
          <svg
            className="w-6 h-6 transition-all duration-300 transform rotate-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2.2"
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
        )}

        {/* Unread Alert Badge */}
        {showBadge && !isOpen && (
          <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-red-500 border border-white"></span>
          </span>
        )}
      </button>
    </div>
  );
};

export default HelpChat;
