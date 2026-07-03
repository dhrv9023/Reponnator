import React from "react";
import { FlowOption } from "./chatFlow";
import { CustomOption } from "./useChat";

interface OptionButtonsProps {
  options: (FlowOption | CustomOption)[];
  selectedOption: FlowOption | CustomOption | null;
  isTransitioning: boolean;
  onSelect: (option: FlowOption | CustomOption) => void;
  onStartOver: () => void;
}

export const OptionButtons: React.FC<OptionButtonsProps> = ({
  options,
  selectedOption,
  isTransitioning,
  onSelect,
  onStartOver,
}) => {
  // Special case: Empty options array (end node)
  if (options.length === 0) {
    return (
      <div className="flex justify-center px-4 pb-4 w-full">
        <button
          onClick={onStartOver}
          className="w-full max-w-[200px] py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 active:scale-95 transition-all duration-150 shadow-md text-center flex items-center justify-center gap-1.5 cursor-pointer"
        >
          <span>Start over</span>
          <span>🔄</span>
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 px-4 pb-4 w-full">
      {options.map((option, idx) => {
        const isThisSelected = selectedOption === option;
        
        // Button styles based on active selection transition
        let btnClasses = "w-full flex items-center justify-between text-left px-4 py-2.5 rounded-xl text-sm font-medium border text-indigo-700 bg-white border-indigo-100 hover:bg-indigo-50/50 hover:border-indigo-300 active:scale-[0.98] transition-all duration-150 shadow-sm cursor-pointer";
        
        if (isTransitioning) {
          if (isThisSelected) {
            btnClasses = "w-full flex items-center justify-between text-left px-4 py-2.5 rounded-xl text-sm font-medium border bg-indigo-600 border-indigo-600 text-white shadow-md scale-[0.98] transition-all duration-150";
          } else {
            btnClasses = "w-full flex items-center justify-between text-left px-4 py-2.5 rounded-xl text-sm font-medium border border-gray-100 text-gray-400 bg-gray-50/50 opacity-40 transition-all duration-150 pointer-events-none";
          }
        }

        return (
          <button
            key={idx}
            onClick={() => !isTransitioning && onSelect(option)}
            disabled={isTransitioning}
            className={btnClasses}
          >
            <span className="pr-2 truncate">{option.label}</span>
            <span className={`text-base font-semibold select-none flex-shrink-0 ${isThisSelected && isTransitioning ? 'text-white' : 'text-indigo-400'}`}>
              →
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default OptionButtons;
