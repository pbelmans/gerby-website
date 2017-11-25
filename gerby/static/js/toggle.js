$(document).ready(function() {
  // we do this in JS as it only makes sense to have these when JS is enabled
  $("div#burger-content").append("<input type='radio' class='toggle-numbering' name='burger-toggle-numbering' value='burger-toggle-numbers' id='burger-toggle-numbers' checked><label for='burger-toggle-numbers'>show numbers</label><br>")
  $("div#burger-content").append("<input type='radio' class='toggle-numbering' name='burger-toggle-numbering' value='burger-toggle-tags' id='burger-toggle-tags'><label for='burger-toggle-tags'>show tags</label>")

  $("section#meta").append("<input type='radio' class='toggle-numbering' name='meta-toggle-numbering' value='meta-toggle-numbers' id='meta-toggle-numbers' checked><label for='meta-toggle-numbers'>show numbers</label><br>")
  $("section#meta").append("<input type='radio' class='toggle-numbering' name='meta-toggle-numbering' value='meta-toggle-tags' id='meta-toggle-tags'><label for='meta-toggle-tags'>show tags</label>")

  $("input[type=radio][class=toggle-numbering]").on("change", function() {
    // the actual toggle
    $("*[data-tag]").each(function(index, reference) {
      $(reference).toggleClass("tag");

      var value = $(reference).attr("data-tag");
      $(reference).attr("data-tag", $(reference).text())
      $(reference).text(value);
    });

    // synchronise the other radio buttons: use presence of tag class
    if ($("*[data-tag]").hasClass("tag"))
      $("input[value$=-toggle-tags]").prop("checked", true);
    else
      $("input[value$=-toggle-numbers]").prop("checked", true);
  });
});
