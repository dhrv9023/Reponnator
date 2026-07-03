import React, { useState } from "react";
import emailjs from "@emailjs/browser";
import { ChatMessage } from "./useChat";

interface EmailFormProps {
  emailSubject: string;
  messages: ChatMessage[];
  onBack: () => void;
  onSuccess: (formData: { email: string; message: string }) => void;
}

export const EmailForm: React.FC<EmailFormProps> = ({
  emailSubject,
  messages,
  onBack,
  onSuccess,
}) => {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [emailError, setEmailError] = useState("");
  const [messageError, setMessageError] = useState("");
  
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState("");

  const validateEmail = (val: string) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!val) {
      return "Email address is required.";
    }
    if (!regex.test(val)) {
      return "Please enter a valid email address.";
    }
    return "";
  };

  const validateMessage = (val: string) => {
    if (!val) {
      return "Message is required.";
    }
    if (val.trim().length < 10) {
      return "Message must be at least 10 characters long.";
    }
    return "";
  };

  const buildConversationText = (chatMessages: ChatMessage[]) => {
    return chatMessages
      .map((msg) => {
        const timeStr = msg.timestamp.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
        return `[${timeStr}] ${msg.type.toUpperCase()}: ${msg.text}`;
      })
      .join("\n");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const eErr = validateEmail(email);
    const mErr = validateMessage(message);

    setEmailError(eErr);
    setMessageError(mErr);

    if (eErr || mErr) {
      return;
    }

    setIsSending(true);
    setSendError("");

    const SERVICE_ID =
      import.meta.env.REACT_APP_EMAILJS_SERVICE_ID ||
      import.meta.env.VITE_EMAILJS_SERVICE_ID ||
      "";
    const TEMPLATE_ID =
      import.meta.env.REACT_APP_EMAILJS_TEMPLATE_ID ||
      import.meta.env.VITE_EMAILJS_TEMPLATE_ID ||
      "";
    const PUBLIC_KEY =
      import.meta.env.REACT_APP_EMAILJS_PUBLIC_KEY ||
      import.meta.env.VITE_EMAILJS_PUBLIC_KEY ||
      "";

    const templateParams = {
      user_email: email,
      subject: `CodeAutopsy Support: ${emailSubject}`,
      message: message,
      conversation: buildConversationText(messages),
      page_url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    try {
      if (!SERVICE_ID || !TEMPLATE_ID || !PUBLIC_KEY) {
        throw new Error("Missing EmailJS environment keys.");
      }

      await emailjs.send(SERVICE_ID, TEMPLATE_ID, templateParams, PUBLIC_KEY);
      
      onSuccess({ email, message });
    } catch (err: any) {
      console.error("EmailJS Error:", err);
      setSendError(
        "Failed to send. Please try contacting support@codeautopsy.com directly."
      );
    } finally {
      setIsSending(false);
    }
  };

  // Keyboard shortcut: Ctrl+Enter to submit
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && e.ctrlKey) {
      handleSubmit(e);
    }
  };

  return (
    <div className="w-full flex-grow flex flex-col p-4 bg-gray-50/50">
      {/* Form Header with Back control */}
      <div className="flex items-center gap-2 mb-4 pb-2 border-b border-gray-100">
        <button
          type="button"
          onClick={onBack}
          disabled={isSending}
          className="flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 active:scale-95 transition-all select-none cursor-pointer"
          title="Back to topics"
        >
          <span className="text-lg font-semibold">←</span>
        </button>
        <div>
          <h3 className="text-sm font-semibold text-gray-800">
            Send Us a Message
          </h3>
          <p className="text-[11px] text-gray-400">
            Subject: {emailSubject}
          </p>
        </div>
      </div>

      {/* Main Form */}
      <form onSubmit={handleSubmit} className="flex-grow flex flex-col justify-between">
        <div className="flex flex-col gap-3.5">
          {/* Email input field */}
          <div className="flex flex-col gap-1">
            <label
              htmlFor="email"
              className="text-xs font-semibold text-gray-600"
            >
              Your Email Address
            </label>
            <input
              type="email"
              id="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (emailError) setEmailError(validateEmail(e.target.value));
              }}
              disabled={isSending}
              className={`w-full px-3 py-2 border rounded-xl text-sm focus:outline-none focus:ring-2 transition-all bg-white ${
                emailError
                  ? "border-red-300 focus:ring-red-100 focus:border-red-500"
                  : "border-gray-200 focus:ring-indigo-100 focus:border-indigo-500"
              }`}
            />
            {emailError && (
              <span className="text-[10px] text-red-500 pl-1">
                {emailError}
              </span>
            )}
          </div>

          {/* Message text area */}
          <div className="flex flex-col gap-1">
            <label
              htmlFor="message"
              className="text-xs font-semibold text-gray-600"
            >
              What can we help you with?
            </label>
            <textarea
              id="message"
              placeholder="Please describe your query here (min 10 chars)..."
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                if (messageError) setMessageError(validateMessage(e.target.value));
              }}
              onKeyDown={handleKeyDown}
              disabled={isSending}
              rows={5}
              className={`w-full px-3 py-2 border rounded-xl text-sm focus:outline-none focus:ring-2 transition-all resize-none bg-white ${
                messageError
                  ? "border-red-300 focus:ring-red-100 focus:border-red-500"
                  : "border-gray-200 focus:ring-indigo-100 focus:border-indigo-500"
              }`}
            />
            <div className="flex items-center justify-between px-1">
              {messageError ? (
                <span className="text-[10px] text-red-500">
                  {messageError}
                </span>
              ) : (
                <span className="text-[10px] text-gray-400">
                  Press Ctrl + Enter to send
                </span>
              )}
              <span className="text-[9px] text-gray-400">
                {message.length} chars
              </span>
            </div>
          </div>
        </div>

        {/* Action Button & Send error details */}
        <div className="flex flex-col gap-2 mt-4">
          {sendError && (
            <div className="p-2.5 bg-red-50 border border-red-100 text-red-600 rounded-xl text-[11px] leading-relaxed shadow-sm">
              {sendError}
            </div>
          )}

          <button
            type="submit"
            disabled={isSending}
            className="w-full py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 active:scale-95 disabled:bg-indigo-400 disabled:pointer-events-none transition-all duration-150 shadow-md flex items-center justify-center gap-2 cursor-pointer select-none"
          >
            {isSending ? (
              <>
                <svg
                  className="animate-spin h-4 w-4 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                <span>Sending...</span>
              </>
            ) : (
              <span>Send Message</span>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default EmailForm;
