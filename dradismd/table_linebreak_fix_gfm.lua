function removeLineBreaks(elem)
  if elem.t == 'Plain' then
    local newContent = {}
    for _, item in ipairs(elem.content) do
      -- Check if the item is a LineBreak
      if item.t == 'LineBreak' then
        table.insert(newContent, pandoc.Str("{{linebreak}}"))
      else
        -- Add other items to the new content
        table.insert(newContent, item)
      end
    end

    -- Update the content of the Plain element
    elem.content = newContent
  end

  return elem
end

return {
  {Plain = removeLineBreaks}
}