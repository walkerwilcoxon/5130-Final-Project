import python

from Call c
where c.getFunc().(Name).getId() = "print"
select c, 
    c.getLocation().getStartLine(),
    c.getLocation().getFile().getRelativePath()