import React, { useEffect, useRef } from "react";
import { useChat } from "./useChat";
import MessageBubble from "./MessageBubble";
import OptionButtons from "./OptionButtons";
import TypingIndicator from "./TypingIndicator";
import EmailForm from "./EmailForm";
import { FLOW } from "./chatFlow";

interface ChatWidgetProps {
  chat: ReturnType<typeof useChat>;
  onClose: () => void;
  onMinimize: () => void;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({
  chat,
  onClose,
  onMinimize,
}) => {
  const {
    messages,
    currentNodeId,
    isTyping,
    conversationPath,
    emailSubject,
    showEmailForm,
    customOptions,
    selectedOption,
    isTransitioningOptions,
    handleOptionSelect,
    goBack,
    handleEmailSent,
    resetChat,
    setShowEmailForm,
  } = chat;

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Smooth scroll to the bottom of the messages list
  const scrollToBottom = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, showEmailForm]);

  // Determine back button visibility
  const showBackButton =
    conversationPath.length > 1 && !showEmailForm && currentNodeId !== "root";

  // Determine options to render
  const currentNode = FLOW[currentNodeId];
  const activeOptions = customOptions || (currentNode ? currentNode.options : []);

  // Check if we should render option buttons
  const showOptions = !showEmailForm && !isTyping && activeOptions && currentNodeId !== "end" && currentNodeId !== "ask_ai";

  return (
    <div className="flex flex-col w-full h-full bg-white rounded-2xl overflow-hidden shadow-2xl border border-gray-100/80 animate-widget-in">
      {/* Header Section */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 text-white select-none">
        <div className="flex items-center gap-2.5">
          {/* Holographic Logo Icon */}
          <div className="w-9 h-9 rounded-xl bg-white/10 backdrop-blur-md flex items-center justify-center border border-white/20 text-base font-bold shadow-inner">
            💀
          </div>
          <div>
            <h2 className="text-sm font-bold tracking-wide flex items-center gap-1.5 leading-none mb-1">
              CodeAutopsy Help
              <span className="w-2 h-2 rounded-full bg-green-400 border border-indigo-600 inline-block shadow-sm" title="Online" />
            </h2>
            <p className="text-[10px] text-indigo-100/90 font-medium">
              Typically replies instantly
            </p>
          </div>
        </div>

        {/* Header Controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={onMinimize}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/10 active:scale-95 transition-all text-white font-bold cursor-pointer"
            title="Minimize"
          >
            —
          </button>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/10 active:scale-95 transition-all text-white text-lg font-medium cursor-pointer"
            title="Close"
          >
            ×
          </button>
        </div>
      </div>

      {/* Conditional Content Area */}
      {showEmailForm ? (
        <EmailForm
          emailSubject={emailSubject}
          messages={messages}
          onBack={() => setShowEmailForm(false)}
          onSuccess={handleEmailSent}
        />
      ) : (
        <div className="flex-grow flex flex-col min-h-0 bg-[#F8F9FA]">
          {/* Scrollable Messages Area */}
          <div
            ref={scrollContainerRef}
            className="flex-grow overflow-y-auto px-4 pt-4 pb-2 flex flex-col chat-scroll"
          >
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {isTyping && <TypingIndicator />}
          </div>

          {/* Controls / Options Area */}
          <div className="bg-gradient-to-t from-white via-white to-transparent pt-3">
            {/* Back button */}
            {showBackButton && (
              <button
                onClick={goBack}
                className="mx-4 mb-2 flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors select-none cursor-pointer outline-none"
              >
                ← Back
              </button>
            )}

            {/* Answer Options */}
            {showOptions && (
              <OptionButtons
                options={activeOptions}
                selectedOption={selectedOption}
                isTransitioning={isTransitioningOptions}
                onSelect={handleOptionSelect}
                onStartOver={resetChat}
              />
            )}

            {/* AI Manual Q&A Input Box */}
            {currentNodeId === "ask_ai" && !isTyping && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const input = form.elements.namedItem("manualQuestion") as HTMLInputElement;
                  if (input && input.value.trim()) {
                    chat.handleManualQuestion(input.value.trim());
                    input.value = "";
                  }
                }}
                className="flex items-center gap-2 px-4 pb-4 pt-1 border-t border-gray-100/60 animate-fade-in"
              >
                <input
                  name="manualQuestion"
                  type="text"
                  placeholder="Type a question about the project..."
                  required
                  className="flex-grow px-3.5 py-2.5 text-[11px] border border-gray-200 focus:border-indigo-500 rounded-xl focus:outline-none bg-[#F8F9FA] placeholder-gray-400/80 font-medium transition-all"
                  autoComplete="off"
                />
                <button
                  type="submit"
                  className="px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 text-white rounded-xl text-[11px] font-bold transition-all shadow-sm active:scale-95 cursor-pointer"
                >
                  Send
                </button>
              </form>
            )}

            {/* End Node State */}
            {currentNodeId === "end" && !isTyping && (
              <OptionButtons
                options={[]}
                selectedOption={null}
                isTransitioning={false}
                onSelect={() => {}}
                onStartOver={resetChat}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatWidget;
